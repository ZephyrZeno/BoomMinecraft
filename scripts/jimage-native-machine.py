"""Seal complete canonical COFF for the two unregistered JIMAGE candidates.

This supplements their source receipts; it does not verify Java selection or
execute a native adapter. Section flags and complete symbol records matter in
addition to instructions and named relocation targets.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom/jimage-native-map'
ASSEMBLER=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')
KINDS={
    'map':('jimage-native-map-candidate','source-jimage-native-map-candidate'),
    'library':('native-library-jimage-candidate','source-native-library-self-jimage-variant'),
}


def module(name):
    spec=importlib.util.spec_from_file_location('jimage_complete_machine_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source')
O=module('jimage-owner-candidate')


def checked(record):
    path=Path(record['path']).resolve()
    S.check(path.is_relative_to(ROOT) or path.is_relative_to(Path('D:/Dev')),
        'Complete machine input escaped project/tool roots')
    S.check(S.artifact(path)==record,'Complete machine input changed: '+str(path))
    return path


def verify(candidate_file,kind,output):
    candidate_file=Path(candidate_file).resolve();output=Path(output).resolve()
    S.check(kind in KINDS and candidate_file.is_relative_to(ART),'Unknown or nonisolated JIMAGE candidate')
    S.check(output.is_relative_to(ART) and not output.exists(),'Fresh isolated complete machine directory required')
    name,family=KINDS[kind];C=module(name);row=S.read(candidate_file)
    S.check(row['schema']==1 and row['family']==family and all(row.get(k) is False for k in
        ('registered','linked','executed','game_started')),'Unregistered candidate machine scope differs')
    for key,path in [('tool',Path(C.__file__)),('model',Path(C.C.__file__)),('kernel',C.KERNEL),('assembler',ASSEMBLER)]:
        S.check(row[key]==S.artifact(path),'Current machine source/tool differs: '+key)
    source=S.checked(row['assembly']);actual=S.checked(row['object'])
    text,exports,imports=C.assembly(row['metadata'])[:3]
    S.check(source.read_text(encoding='utf-8')==text and row['exports']==sorted(exports) and row['imports']==sorted(imports),
        'Canonical machine assembly or source symbol declarations differ')
    inputs=[S.artifact(candidate_file),row['assembly'],row['object'],row['tool'],row['model'],row['kernel'],row['assembler'],
        S.artifact(__file__),S.artifact(O.__file__)]
    inputs+=list(row['metadata']['source_helpers'].values())
    if kind=='library':
        inputs.append(row['metadata']['source']['original_kernel'])
    for record in inputs:checked(record)
    output.mkdir(parents=True);assembly,obj=output/'canonical.asm',output/'canonical.obj'
    assembly.write_text(text,encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([str(ASSEMBLER),'/nologo','/c','/Fo'+str(obj),str(assembly)],
            stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    observed,expected=O.normalized_coff(actual),O.normalized_coff(obj)
    S.check(observed==expected,'Complete JIMAGE COFF code/data/flags/symbols/aux/relocations/unwind differ')
    S.check(set(observed['exports'])==exports and set(observed['imports'])==imports,
        'Complete physical symbol declarations differ')
    for record in inputs:checked(record)
    proof=dict(schema=1,verified=True,scope='complete_nondebug_JIMAGE_candidate_COFF_only',kind=kind,
        candidate=S.artifact(candidate_file),inputs=inputs,canonical_assembly=S.artifact(assembly),
        canonical_object=S.artifact(obj),normalized_sha256=hashlib.sha256(
            json.dumps(observed,sort_keys=True,separators=(',',':')).encode()).hexdigest(),normalized=observed,
        section_flags_verified=True,complete_symbol_values_types_storage_and_auxiliary_bytes_verified=True,
        all_code_data_relocations_and_unwind_verified=True,
        original_source_receipt_replaced=False,Java_selection_reverified=False,normal_native_adapter_executed=False,
        linked=False,registered=False,game_started=False)
    path=output/'verification.json';S.write(path,proof);return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--kind',choices=tuple(KINDS),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(verify(a.candidate,a.kind,a.output))
