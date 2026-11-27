"""Two unregistered pure-ASM initIDs objects with fresh complete COFF proof.

This is source projection plus normal Frame/data binding and actual assembler
verification. No source V, PE link, JVM, Main, or provider registration runs.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'AGENTS.md').is_file())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result);return result


N=module('normal_RFID_source',HERE/'random-access-file-initids-source.py')
O=module('normal_RFID_complete_COFF',ROOT/'scripts/jimage-owner-candidate.py')
check,artifact,checked,read=N.check,N.artifact,N.checked,N.read
KERNEL=N.KERNEL


def write(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(value,indent=2)+'\n')


def fresh(output):
    output=Path(output).resolve();check(output.is_relative_to(ROOT/'.boom') and not output.exists(),'Fresh isolated .boom output required')
    output.mkdir(parents=True);return output


def producers():return {key:artifact(value) for key,value in (
    ('candidate',Path(__file__)),('model',Path(N.__file__)),('kernel',KERNEL),('COFF_reader',Path(O.__file__)))}


def sources(meta):return dict(native=N.normal_frames(meta),registry=N.registry(meta))


def assemble(output,assembler,texts):
    result={}
    for name,(text,exports,imports) in texts.items():
        asm,obj=output/(name+'.asm'),output/(name+'.obj')
        asm.write_text(text,encoding='utf-8',newline='\n')
        with (output/(name+'.log')).open('xb') as log:
            process=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=log,stderr=subprocess.STDOUT,timeout=120)
        write(output/(name+'-status.json'),dict(natural_exit_code=process.returncode))
        check(process.returncode==0,'Actual ML64 failure preserved: '+name)
        machine=O.normalized_coff(obj)
        check(set(machine['exports'])==exports and set(machine['imports'])==imports,'Actual source PROC/data declarations differ: '+name)
        result[name]=dict(assembly=artifact(asm),object=artifact(obj),exports=sorted(exports),imports=sorted(imports))
    return result


def verify(candidate_file,output):
    candidate_file=Path(candidate_file).resolve();before=artifact(candidate_file);candidate=read(candidate_file)
    check(candidate['schema']==1 and candidate['family']=='source-random-access-file-initids-candidate' and
        candidate['producers']==producers() and all(candidate[key] is False for key in
            ('registered','linked','executed','game_started','runtime_acceptance_complete')),'Current independent candidate source/scope differs')
    args=candidate['binding_inputs']
    for row in candidate['inputs']:checked(row)
    meta=N.bind(checked(args['state']),checked(args['source_selection']),checked(args['parent_overlay']),args['pinned_directory'],checked(args['field_records_source']),checked(args['release']))
    check(meta==candidate['metadata']==read(checked(candidate['model'])),'Current original source/normal layout/Frame/Code projection differs')
    text=sources(meta);check(set(candidate['units'])==set(text)=={'native','registry'},'Exactly two canonical objects required')
    output=fresh(output);canonical=assemble(output,checked(candidate['assembler']),text);machines={}
    for name,(expected,exports,imports) in text.items():
        actual=candidate['units'][name];check(checked(actual['assembly']).read_text(encoding='utf-8')==expected and
            actual['exports']==sorted(exports) and actual['imports']==sorted(imports),'Canonical source or declared ABI differs: '+name)
        observed=O.normalized_coff(checked(actual['object']));rebuilt=O.normalized_coff(checked(canonical[name]['object']))
        check(observed==rebuilt,'Complete actual/canonical sections/code/data/flags/symbol aux/relocations/unwind differ: '+name)
        machines[name]=dict(actual=actual['object'],canonical_assembly=canonical[name]['assembly'],canonical_object=canonical[name]['object'],
            normalized_sha256=hashlib.sha256(json.dumps(observed,sort_keys=True,separators=(',',':')).encode()).hexdigest(),normalized=observed,
            all_nondebug_bytes_section_flags_symbol_values_types_storage_aux_relocations_and_unwind_equal=True)
    for row in candidate['inputs']:checked(row)
    checked(before)
    proof=dict(schema=1,verified=True,scope='unregistered_RandomAccessFile_initIDs_original_source_normal_Frame_and_complete_COFF_only',
        candidate=before,verifier=artifact(__file__),producers=producers(),complete_machine=machines,
        source_native_declarations=1,source_classes=2,JNI_initialized_declaring_classes=1,registered_source_fields=1,
        FileDescriptor_class_initialization_added=False,IO_operations_implemented=False,Java_oop_root_cells_added=0,
        original_source_class_ids_and_Code_unchanged=True,normal_FieldIDs_are_original_FMAP_address_PROCs=True,
        source_V_repeated=False,existing_source_Frame_verified_by_original_class_flags_and_actual_record_bytes=True,
        whole_Frame_source_V_or_reassembly_repeated=False,PE_linked=False,guest_or_JVM_or_Main_executed=False,
        registered=False,runtime_acceptance_complete=False,game_started=False)
    path=output/'verification.json';write(path,proof);return path


def build(args):
    check(args.assembler.is_file(),'Explicit installed assembler required')
    binding={key:artifact(path) for key,path in (('state',args.state),('source_selection',args.source),('parent_overlay',args.parent))}
    binding['pinned_directory']=str(args.pinned.resolve())
    binding['field_records_source']=artifact(args.field_records_source)
    binding['release']=artifact(args.release)
    meta=N.bind(args.state,args.source,args.parent,args.pinned,args.field_records_source,args.release)
    inputs=list(meta['inputs'])+list(producers().values())+[artifact(args.assembler)]
    inputs += [artifact(ROOT/name) for name in meta['tool_sources']]
    output=fresh(args.output);write(output/'model.json',meta);units=assemble(output,args.assembler.resolve(),sources(meta))
    for row in inputs:checked(row)
    candidate=output/'candidate.json'
    write(candidate,dict(schema=1,family='source-random-access-file-initids-candidate',producers=producers(),binding_inputs=binding,
        metadata=meta,model=artifact(output/'model.json'),units=units,assembler=artifact(args.assembler),inputs=inputs+[artifact(output/'model.json')],
        registered=False,linked=False,executed=False,game_started=False,runtime_acceptance_complete=False))
    proof=verify(candidate,output/'canonical')
    write(output/'verification.json',read(proof))
    print(json.dumps(dict(candidate=artifact(candidate),verification=artifact(output/'verification.json')),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='action',required=True)
    p=subs.add_parser('build')
    for name in ('state','source','parent','pinned','field-records-source','release','assembler','output'):p.add_argument('--'+name,type=Path,required=True)
    p=subs.add_parser('verify');p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='build':build(args)
    else:print(json.dumps(artifact(verify(args.candidate,args.output)),indent=2))


if __name__=='__main__':main()
