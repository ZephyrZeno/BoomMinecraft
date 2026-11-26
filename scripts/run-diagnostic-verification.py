"""Run or repeat strict verification of an existing diagnostic image without rebuilding it."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid


VERIFIER = Path(__file__).resolve().with_name('verify-diagnostic-closure.py')


def write_status(path, record):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def verify(directory):
    directory = Path(directory).resolve()
    with (directory / 'selection-verification.lock').open('a+b') as lock:
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run_attempt(directory)


def run_attempt(directory):
    start = time.monotonic()
    attempt = directory / 'verification-attempts' / uuid.uuid4().hex
    attempt.mkdir(parents=True)
    stdout, stderr = attempt / 'stdout.log', attempt / 'stderr.log'
    candidate = attempt / 'proof.json'
    status = dict(state='starting', started_utc=datetime.now(timezone.utc).isoformat(),
                  directory=str(attempt), runner_pid=os.getpid(), verifier=str(VERIFIER),
                  stdout=str(stdout), stderr=str(stderr), exit_code=None)
    status_file = directory / 'selection-verification-status.json'

    def save():
        write_status(attempt / 'status.json', status)
        write_status(status_file, status)

    save()
    try:
        with stdout.open('wb') as out, stderr.open('wb') as err:
            command = [sys.executable, '-X', 'faulthandler', '-u', str(VERIFIER), str(directory), '--output', str(candidate)]
            with subprocess.Popen(command, stdout=out, stderr=err) as child:
                try:
                    status.update(state='running', verifier_pid=child.pid)
                    save()
                    code = child.wait()
                except BaseException:
                    child.kill()
                    child.wait()
                    raise
        status.update(exit_code=code, exit_hex=f'0x{code & 0xffffffff:08x}')
        if code:
            raise ValueError(f"Verifier exited with {code} ({status['exit_hex']})")
        proof = json.loads(candidate.read_bytes())
        if (not isinstance(proof, dict) or proof.get('verified') is not True or proof.get('diagnostic_only') is not True or
                proof.get('source_closure_complete') is not False):
            raise ValueError('Verifier returned an incomplete diagnostic receipt')
        # Keep the receipt in the attempt as well. Readers only see a complete
        # successful result, including when a replay of an older image fails.
        staged = attempt / 'publish.tmp'
        shutil.copyfile(candidate, staged)
        staged.replace(directory / 'selection-verification.json')
        status['state'] = 'verified'
    except (OSError, ValueError, KeyboardInterrupt) as error:
        status.update(state='failed', error=type(error).__name__ + ': ' + str(error))
    finally:
        status['elapsed_seconds'] = round(time.monotonic() - start, 3)
        save()
        for log, suffix in ((stdout, 'log'), (stderr, 'err')):
            if log.exists():
                staged = attempt / ('publish-' + suffix + '.tmp')
                shutil.copyfile(log, staged)
                staged.replace(directory / ('selection-verification.' + suffix))
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    result = verify(parser.parse_args().directory)
    print(json.dumps(result))
    raise SystemExit(0 if result['state'] == 'verified' else 1)
