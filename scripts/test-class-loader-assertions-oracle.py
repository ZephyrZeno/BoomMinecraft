"""Check ClassLoader assertion snapshots in the locked development JDK only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import uuid


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'java/reference/ClassLoaderAssertionsReference.java'


def check(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), size=path.stat().st_size, sha256=checksum)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def checked(record):
    path = Path(record['path']).resolve()
    actual = digest(path)
    check(all(actual[key] == record['digest'][key] for key in ('size', 'sha256')),
          'Locked input changed: ' + str(path))
    return path


def run(command, directory, name):
    result = subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True,
                            timeout=40, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (directory / (name + '.out.log')).write_bytes(result.stdout)
    (directory / (name + '.err.log')).write_bytes(result.stderr)
    check(result.returncode == 0, 'Oracle process failed; inspect ' + str(directory / name))
    return result.stdout.decode('utf-8')


def verify_row(row, application, system, classes, packages):
    check(row['application_probe'] is application and row['system_probe'] is system,
          'User/system assertion configuration was conflated')
    check(row['independent_snapshot_objects'] == 10, 'Directive snapshots share VM objects')
    actual = row['directives']
    check(actual['deflt'] is application, 'retrieveDirectives.deflt is not the user default')
    for names, flags, expected in (('classes', 'classEnabled', classes),
                                   ('packages', 'packageEnabled', packages)):
        check(len(actual[names]) == len(actual[flags]) == len(expected) and
              dict(zip(actual[names], actual[flags])) == expected,
              'Original assertion overrides differ: ' + names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    batch = args.batch.resolve()
    check(batch.is_relative_to(ROOT / '.boom'), 'Use a project batch')
    summary = read(batch / 'summary.json')
    catalog = checked(summary['frames']['original_system_catalog'])
    image = checked(read(catalog)['image'])
    java = args.java.resolve()
    javac = java.with_name('javac.exe')
    check(java.name.lower() == 'java.exe' and
          (java.parent.parent / 'lib/modules').resolve() == image,
          'Oracle must use the batch-locked development JDK')
    output = (args.output or ROOT / '.boom/class-loader-assertions-oracle' / uuid.uuid4().hex).resolve()
    check(output.is_relative_to(ROOT / '.boom') and not output.exists(),
          'Use a fresh isolated project output directory')
    identities = [digest(path) for path in (Path(__file__), SOURCE, java, javac, image,
                                           catalog, batch / 'summary.json')]
    output.mkdir(parents=True)
    run([javac, '-encoding', 'UTF-8', '-d', output, SOURCE], output, 'compile')
    cases = []
    for application in (False, True):
        for system in (False, True):
            for overrides in (False, True):
                options = ['-ea' if application else '-da', '-esa' if system else '-dsa']
                classes, packages = {}, {}
                if overrides:
                    classes = {'boom.oracle.Disabled': False, 'boom.oracle.Enabled': True}
                    packages = {'boom.oracle': True, 'boom.oracle.nested': False}
                    options += ['-ea:boom.oracle...', '-da:boom.oracle.nested...',
                                '-da:boom.oracle.Disabled', '-ea:boom.oracle.Enabled']
                name = 'case-' + str(len(cases))
                command = [java, '--add-opens=java.base/java.lang=ALL-UNNAMED', *options,
                           '-cp', output, 'ClassLoaderAssertionsReference']
                row = json.loads(run(command, output, name))
                verify_row(row, application, system, classes, packages)
                cases.append(dict(application=application, system=system, options=options,
                                  overrides=overrides, observation=row))
    check([digest(item['path']) for item in identities] == identities,
          'Oracle tools or source inputs changed while running')
    report = dict(verified=True, scope='locked_development_JVM_ClassLoader_assertion_snapshots_only',
                  identities=identities, compiled_oracle=digest(output / 'ClassLoaderAssertionsReference.class'),
                  cases=cases, default_profiles=4, override_profiles=4,
                  current_assembly_profile_supports_overrides=False,
                  assembly_runtime_executed=False, game_started=False, world_created=False)
    result = output / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(verified=True, result=digest(result), cases=len(cases), game_started=False)))


if __name__ == '__main__':
    main()
