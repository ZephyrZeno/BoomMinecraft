"""Assemble the two diagnostic translation units and seal their exact COFF inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

UNITS = ('initialization-closure', 'diagnostic-stops')
RECEIPT = 'assembly-provenance.json'


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=sha))


def assemble(directory, assembler, parallel_assembly=False, workers=8, code_mib=8):
    directory, assembler = Path(directory).resolve(), Path(assembler).resolve()
    root = Path(__file__).resolve().parents[1] / '.boom'
    if not directory.is_relative_to(root) or assembler.name.lower() != 'ml64.exe':
        raise ValueError('Expected a project selection and the x64 assembler')
    tool = artifact(assembler)
    if parallel_assembly:
        return assemble_parallel(directory,assembler,tool,workers,code_mib)
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


def assemble_parallel(directory,assembler,tool,workers,code_mib):
    if not 1<=workers<=8 or not 1<=code_mib<=1024:
        raise ValueError('Invalid parallel assembler worker count or source budget')
    helper=module('diagnostic_parallel_source_assembler','parallel-diagnostic-assembly.py')
    before=artifact(directory/'initialization-closure.asm')
    closure=artifact(directory/'closure.json')
    expected=json.loads((directory/'closure.json').read_bytes())['selected_function_sha256']
    output=directory/('parallel-assembly-'+uuid4().hex)
    prepared=helper.prepare(directory/'initialization-closure.asm',output,expected,code_mib*1024*1024)
    assembled=helper.assemble(prepared,assembler,workers)
    parallel_receipt=output/'receipt.json'
    proof=helper.verify(parallel_receipt,directory/'initialization-closure.asm',expected)
    if artifact(directory/'initialization-closure.asm')!=before or artifact(directory/'closure.json')!=closure:
        raise ValueError('Full parallel source selection changed during assembly')
    units=[dict(name='initialization-closure',assembly=before,parallel_receipt=artifact(parallel_receipt),
        parts=[dict(assembly=u['assembly'],object=u['object']) for u in assembled['units']],
        promoted_data=assembled['promoted_data'])]
    source=directory/'diagnostic-stops.asm';obj=source.with_suffix('.obj');source_before=artifact(source)
    with (directory/'diagnostic-stops-assembler.log').open('wb') as log:
        subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(source)],stdout=log,stderr=subprocess.STDOUT,check=True)
    if artifact(source)!=source_before or artifact(assembler)!=tool:
        raise ValueError('Diagnostic source or assembler changed during parallel assembly')
    units.append(dict(name='diagnostic-stops',assembly=source_before,
        parts=[dict(assembly=source_before,object=artifact(obj))],promoted_data=[]))
    receipt=dict(schema=2,assembly_mode='parallel_initialization_source_groups',assembler=tool,units=units,
        source_manifest=closure,parallel_source_proof=proof,monolithic_reference_used=False,monolithic_binary_equivalence=False)
    temporary=directory/(RECEIPT+'.'+uuid4().hex)
    temporary.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    temporary.replace(directory/RECEIPT)
    return receipt


def verify(directory):
    directory = Path(directory).resolve()
    path = directory / RECEIPT
    with path.open('rb') as stream:
        raw = stream.read()
    receipt = json.loads(raw)
    if receipt['schema']==2:
        return verify_parallel(directory,path,raw,receipt)
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


def verify_parallel(directory,path,raw,receipt):
    if (receipt.get('assembly_mode')!='parallel_initialization_source_groups' or
            receipt.get('monolithic_reference_used') is not False or receipt.get('monolithic_binary_equivalence') is not False or
            [u.get('name') for u in receipt['units']]!=list(UNITS)):
        raise ValueError('Unexpected parallel diagnostic provenance scope')
    assembler=Path(receipt['assembler']['path'])
    if assembler.name.lower()!='ml64.exe' or artifact(assembler)!=receipt['assembler']:
        raise ValueError('Parallel diagnostic assembler changed')
    if artifact(directory/'closure.json')!=receipt['source_manifest']:
        raise ValueError('Parallel diagnostic source manifest changed')
    expected=json.loads((directory/'closure.json').read_bytes())['selected_function_sha256']
    helper=module('verify_diagnostic_parallel_source_assembler','parallel-diagnostic-assembly.py')
    flattened=[];logical=[]
    for name,unit in zip(UNITS,receipt['units']):
        if unit['assembly']!=artifact(directory/(name+'.asm')) or not unit['parts']:
            raise ValueError('Parallel diagnostic full source changed: '+name)
        for part in unit['parts']:
            if (not Path(part['assembly']['path']).resolve().is_relative_to(directory) or
                    not Path(part['object']['path']).resolve().is_relative_to(directory) or
                    artifact(part['assembly']['path'])!=part['assembly'] or artifact(part['object']['path'])!=part['object']):
                raise ValueError('Parallel diagnostic part changed or escaped the selection')
        if name=='initialization-closure':
            selected=unit['parallel_receipt']
            if not Path(selected['path']).resolve().is_relative_to(directory) or artifact(selected['path'])!=selected:
                raise ValueError('Parallel helper receipt changed')
            sealed=json.loads(Path(selected['path']).read_bytes())
            proof=helper.verify(Path(selected['path']),directory/(name+'.asm'),expected)
            parts=[dict(assembly=u['assembly'],object=u['object']) for u in sealed['units']]
            if (parts!=unit['parts'] or sealed['assembler']!=receipt['assembler'] or
                    sealed['promoted_data']!=unit['promoted_data'] or proof!=receipt['parallel_source_proof']):
                raise ValueError('Parallel helper source/COFF coverage differs')
        elif (len(unit['parts'])!=1 or unit['parts'][0]!=dict(assembly=unit['assembly'],object=artifact(directory/(name+'.obj'))) or
                unit['promoted_data']):
            raise ValueError('Diagnostic stop source must retain its exact monolithic object')
        flattened.extend(unit['parts'])
        logical.append(dict(name=name,assembly=unit['assembly'],parts=unit['parts'],promoted_data=unit['promoted_data']))
    if len({u['object']['path'] for u in flattened})!=len(flattened):
        raise ValueError('Duplicate parallel object in diagnostic link')
    return dict(schema=2,receipt_sha256=hashlib.sha256(raw).hexdigest(),assembler=receipt['assembler'],
        units=flattened,logical_units=logical,parallel_source_proof=receipt['parallel_source_proof'],
        assembly_mode=receipt['assembly_mode'],monolithic_reference_used=False,monolithic_binary_equivalence=False)


def link_objects(directory):
    return [u['object'] for u in verify(directory)['units']]


def logical_symbols(directory,name,reader):
    """Read every real COFF with the existing reader; only hide proven source-private data."""
    directory=Path(directory)
    if name not in UNITS:raise ValueError('Unknown diagnostic logical translation unit')
    if not (directory/RECEIPT).is_file():return reader(directory/(name+'.obj'))
    sealed=verify(directory)
    if sealed.get('schema',1)==1:return reader(directory/(name+'.obj'))
    [unit]=[u for u in sealed['logical_units'] if u['name']==name]
    defined,undefined=set(),set()
    for part in unit['parts']:
        exports,imports=reader(Path(part['object']['path']))
        if defined&exports:raise ValueError('Duplicate public definition across parallel COFF parts')
        defined.update(exports);undefined.update(imports)
    promoted=unit['promoted_data']
    if not isinstance(promoted,list) or promoted!=sorted(set(promoted)):
        raise ValueError('Parallel data promotion allowlist is not canonical')
    raw=Path(unit['assembly']['path']).read_bytes()
    public={n.decode() for n in re.findall(rb'(?m)^PUBLIC[ \t]+(boom_[A-Za-z0-9_]+)[ \t]*\r?$',raw)}
    if name=='initialization-closure':
        source=module('parallel_symbol_source_ranges','batch-source.py')
        spans=source.procedure_spans(raw);outside=[];last=0
        for begin,end in spans.values():outside.append(raw[last:begin]);last=end
        outside.append(raw[last:])
        data=b''.join(outside)
        data_defs={n.decode() for n in re.findall(rb'(?m)^[ \t]*(boom_[A-Za-z0-9_]+)(?::|[ \t]+(?:LABEL|QWORD|DWORD|WORD|BYTE)\b)',data)}
        if not set(promoted)<=(data_defs-public) or set(promoted)&set(spans) or set(promoted)!=(defined-public):
            raise ValueError('Parallel allowlist hides an extra function, original public symbol or non-source data')
    elif promoted:
        raise ValueError('No private diagnostic function may be promoted or hidden')
    if defined-set(promoted)!=public:
        raise ValueError('Parallel aggregate public definitions differ from complete original source')
    return defined-set(promoted),undefined-defined


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--assembler', type=Path, required=True)
    parser.add_argument('--parallel-assembly',action='store_true')
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--code-mib',type=int,default=8)
    options = parser.parse_args()
    assemble(options.directory, options.assembler,options.parallel_assembly,options.workers,options.code_mib)
