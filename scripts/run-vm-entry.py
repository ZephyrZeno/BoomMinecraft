"""Run one explicitly verified native VM entry in its owned isolated process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def check(value,message):
    if not value:raise ValueError(message)

def artifact(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return dict(path=str(path),digest=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))

def read(path):return json.loads(Path(path).read_bytes())

def kill_owned(child,directory):
    """Only terminate this still-owned child tree, then reap its process."""
    if child.poll() is not None:return
    if os.name=='nt':
        taskkill=Path(os.environ['SystemRoot'])/'System32/taskkill.exe'
        with (directory/'owned-kill.log').open('xb') as log:
            result=subprocess.run([str(taskkill),'/PID',str(child.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and child.poll() is None:
            child.kill();child.wait();raise RuntimeError('Owned child tree termination failed; log is preserved')
    else:os.killpg(child.pid,signal.SIGKILL)
    child.wait()

def preflight(root,directory,accepted):
    root,directory=Path(root).resolve(),Path(directory).resolve()
    check(directory.is_relative_to(root/'.boom/vm-entry-images'),'Native entry requires isolated project output')
    proof_file=directory/'verification.json';manifest_file=directory/'vm-entry.json'
    proof,manifest=read(proof_file),read(manifest_file)
    check(artifact(proof_file)['digest']['sha256']==accepted and proof.get('verified') is True and
        proof.get('managed_execution_host') is False and proof.get('full_VM_bootstrap') is False and proof.get('game_started') is False,
        'Explicitly accepted native entry proof differs')
    check(artifact(manifest_file)['digest']['sha256']==proof['source_manifest_sha256'],'Native source manifest changed')
    for name in ('execution.json','vm-entry-status.bin','process.out.log','process.err.log','run-intent.json','run-failure.json','owned-kill.log'):
        check(not (directory/name).exists(),'Native execution evidence is immutable: '+name)
    records=[*manifest['inputs'],*[manifest[k] for k in ('executable','runtime','assembly','link_response')],*manifest['reassembled_objects']]
    records.extend(artifact(path) for path in (proof_file,manifest_file,root/'scripts/decode-vm-entry-report.py',Path(__file__)))
    expected=artifact(__file__)
    check(expected in manifest['inputs'],'Native image did not seal this actual process runner')
    for row in records:check(artifact(row['path'])==row,'Native execution input changed: '+row['path'])
    return manifest,records

def run(root,directory,accepted,observe_source_admissions=False):
    root,directory=Path(root).resolve(),Path(directory).resolve()
    manifest,records=preflight(root,directory,accepted)
    intent=dict(schema=1,scope='owned_native_vm_prefix_execution',accepted_verification_sha256=accepted,
        runner=artifact(__file__),inputs=records,timeout_seconds=45,
        source_admissions_observed=bool(observe_source_admissions),started=False)
    with (directory/'run-intent.json').open('x',encoding='utf-8') as stream:json.dump(intent,stream,indent=2);stream.write('\n')
    started=time.monotonic();child=None
    try:
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        with (directory/'process.out.log').open('xb') as out,(directory/'process.err.log').open('xb') as err:
            child=subprocess.Popen([manifest['executable']['path']],cwd=directory,stdout=out,stderr=err,creationflags=flags,
                start_new_session=os.name!='nt')
            try:exit_code=child.wait(timeout=45)
            except BaseException:
                kill_owned(child,directory);raise
        for row in records:check(artifact(row['path'])==row,'Native input changed after the owned process: '+row['path'])
        command=[sys.executable,str(root/'scripts/decode-vm-entry-report.py'),'--manifest',str(directory/'vm-entry.json'),
            '--report',str(directory/'vm-entry-status.bin'),'--exit-code',str(exit_code),
            '--accepted-verification-sha256',accepted,'--output',str(directory/'execution.json')]
        if observe_source_admissions:command.append('--observe-source-admissions')
        result=subprocess.run(command,cwd=root,creationflags=flags)
        check(result.returncode==0,'Native report protocol validation failed; binary report is preserved')
        for row in records:check(artifact(row['path'])==row,'Native input changed after decoding: '+row['path'])
        return directory/'execution.json'
    except BaseException as error:
        failure=dict(schema=1,error=type(error).__name__,message=str(error),owned_pid=child.pid if child else None,
            exit_code=child.poll() if child else None,elapsed_seconds=time.monotonic()-started,
            original_intent=artifact(directory/'run-intent.json'),reports_preserved=True)
        with (directory/'run-failure.json').open('x',encoding='utf-8') as stream:json.dump(failure,stream,indent=2);stream.write('\n')
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--accepted-verification-sha256',required=True)
    parser.add_argument('--observe-source-admissions',action='store_true')
    args=parser.parse_args();print(run(args.root,args.directory,args.accepted_verification_sha256,args.observe_source_admissions))

if __name__=='__main__':main()
