"""Assemble the two diagnostic translation units and seal their exact COFF inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from uuid import uuid4

UNITS = ('initialization-closure', 'diagnostic-stops')
RECEIPT = 'assembly-provenance.json'


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def assemble(directory, assembler):
    directory, assembler = Path(directory).resolve(), Path(assembler).resolve()
    root = Path(__file__).resolve().parents[1] / '.boom'
    if not directory.is_relative_to(root) or assembler.name.lower() != 'ml64.exe':
        raise ValueError('Expected a project selection and the x64 assembler')
    tool = artifact(assembler)
    units = []
    for name in UNITS:
        source, obj = directory / (name + '.asm'), directory / (name + '.obj')
        before = artifact(source)
        with (directory / (name + '-assembler.log')).open('wb') as log:
            subprocess.run([str(assembler), '/nologo', '/c', '/Fo' + str(obj), str(source)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if artifact(source) != before:
            raise ValueError('Assembly source changed during ml64: ' + name)
        units.append(dict(assembly=before, object=artifact(obj)))
    if artifact(assembler) != tool:
        raise ValueError('Assembler changed during source selection')
    receipt = dict(schema=1, assembler=tool, units=units)
    temporary = directory / (RECEIPT + '.' + uuid4().hex)
    temporary.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    temporary.replace(directory / RECEIPT)


def verify(directory):
    directory = Path(directory).resolve()
    path = directory / RECEIPT
    with path.open('rb') as stream:
        raw = stream.read()
    receipt = json.loads(raw)
    if receipt['schema'] != 1 or len(receipt['units']) != len(UNITS):
        raise ValueError('Unexpected diagnostic assembly provenance format')
    assembler = Path(receipt['assembler']['path'])
    if assembler.name.lower() != 'ml64.exe' or artifact(assembler) != receipt['assembler']:
        raise ValueError('Diagnostic assembly provenance tool differs')
    for name, unit in zip(UNITS, receipt['units']):
        for key, suffix in (('assembly', '.asm'), ('object', '.obj')):
            if unit[key] != artifact(directory / (name + suffix)):
                raise ValueError('Diagnostic assembly provenance differs: ' + name + suffix)
    return dict(receipt_sha256=hashlib.sha256(raw).hexdigest(), assembler=receipt['assembler'], units=receipt['units'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--assembler', type=Path, required=True)
    options = parser.parse_args()
    assemble(options.directory, options.assembler)
