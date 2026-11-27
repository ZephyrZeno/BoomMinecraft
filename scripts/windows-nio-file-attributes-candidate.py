"""Build/verify four source-bound GetFileAttributesEx0 ASM objects.

Inputs are explicit. This tool never selects Java, repeats source V, links a
PE, runs a guest/JVM, or registers a provider family.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
SCRIPT_DIRECTORY=Path(__file__).resolve().parent
ROOT=next(p for p in SCRIPT_DIRECTORY.parents if (p/'AGENTS.md').is_file())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


N=module('normal_WFAT_source',SCRIPT_DIRECTORY/'windows-nio-file-attributes-source.py')
O=module('normal_WFAT_complete_COFF',ROOT/'scripts/jimage-owner-candidate.py')
NR=module('normal_WFAT_physical_roots',ROOT/'scripts/provider-native-roots.py')
check,artifact,checked,read=N.check,N.artifact,N.checked,N.read


def write(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')


def fresh(output):
    output=Path(output).resolve()
    check(output.is_relative_to(ROOT/'.boom') and not output.exists(),'Fresh isolated .boom output required')
    output.mkdir(parents=True);return output


def producers():
    return {name:artifact(path) for name,path in (
        ('candidate',Path(__file__)),('model',Path(N.__file__)),('query',N.QUERY),('error',N.ERROR),('span',N.SPAN),
        ('ABI',N.ABI),('native_owner_kernel',N.CORE),('field_record_reader',N.FIELD_MODEL),
        ('complete_COFF_reader',Path(O.__file__)),('physical_root_reader',Path(NR.__file__)))}


def sources(metadata):return N.unit_sources(metadata)


def assemble(output,assembler,texts):
    result={}
    for name,(text,exports,imports) in texts.items():
        asm,obj=output/(name+'.asm'),output/(name+'.obj')
        asm.write_text(text,encoding='utf-8',newline='\n')
        with (output/(name+'.log')).open('xb') as log:
            process=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],
                stdout=log,stderr=subprocess.STDOUT,timeout=120)
        write(output/(name+'-status.json'),dict(natural_exit_code=process.returncode))
        check(process.returncode==0,'Actual ML64 failure preserved: '+name)
        parsed=O.normalized_coff(obj)
        check(set(parsed['exports'])==exports and set(parsed['imports'])==imports,'Actual source declarations differ: '+name)
        result[name]=dict(assembly=artifact(asm),object=artifact(obj),exports=sorted(exports),imports=sorted(imports))
    return result


def physical(units,metadata):
    return NR.verify_object(checked(units['query']['object']),metadata['native_root_spans'],
        assembly=checked(units['query']['assembly']))


def verify(candidate_file,output):
    candidate_file=Path(candidate_file).resolve();before=artifact(candidate_file);candidate=read(candidate_file)
    check(candidate['schema']==1 and candidate['family']=='source-windows-nio-file-attributes-candidate' and
        candidate['producers']==producers() and all(candidate[key] is False for key in
            ('registered','linked','executed','game_started','runtime_acceptance_complete')),
        'Current candidate source/scope differs')
    for row in candidate['inputs']:checked(row)
    args=candidate['binding_inputs']
    metadata=N.bind(checked(args['state']),checked(args['source_selection']),checked(args['parent_overlay']),
        checked(args['pinned_C']),checked(args['slot_ABI']))
    check(candidate['metadata']==metadata,'Current independent original class/Code/Frame/ABI/dependency projection differs')
    texts=sources(metadata)
    check(set(texts)==set(candidate['units'])=={'native','error','query','span'},'Exactly four independent units required')
    output=fresh(output);canonical=assemble(output,checked(candidate['assembler']),texts)
    complete={};exported=[]
    for name,(text,exports,imports) in texts.items():
        actual=candidate['units'][name];rebuilt=canonical[name]
        check(checked(actual['assembly']).read_text(encoding='utf-8')==text and
            actual['exports']==sorted(exports) and actual['imports']==sorted(imports),'Actual source/import/export contract differs: '+name)
        observed=O.normalized_coff(checked(actual['object']))
        check(observed==O.normalized_coff(checked(rebuilt['object'])),
            'Complete code/data/section flags/symbol values/types/storage/aux/relocations/unwind differ: '+name)
        complete[name]=dict(actual=actual['object'],canonical_assembly=rebuilt['assembly'],canonical_object=rebuilt['object'],
            normalized_sha256=hashlib.sha256(json.dumps(observed,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            normalized=observed,all_nondebug_bytes_flags_symbols_aux_relocations_unwind_equal=True)
        exported+=actual['exports']
    check(len(exported)==len(set(exported)),'Four units must not define duplicate exports')
    roots=physical(candidate['units'],metadata)
    check(roots==candidate['physical_roots'],'Actual 256-QWORD bank/zero/section geometry differs')
    for row in candidate['inputs']:checked(row)
    checked(before)
    proof=dict(schema=1,verified=True,scope='unregistered_GetFileAttributesEx0_original_source_normal_Frame_four_complete_COFF_and_physical_roots_only',
        candidate=before,verifier=artifact(__file__),producers=producers(),complete_machine=complete,physical_roots=roots,
        emitted_original_native_declarations=1,implemented_native_operations=[0],normal_source_classes=7,original_error_constructor_upcalls=1,
        native_slots=256,native_slot_bytes=192,native_root_cells=256,native_root_directory_is_not_itself_a_root=True,
        required_external_native_dependencies=metadata['external_native_dependencies'],
        source_V_repeated=False,original_Java_or_metadata_modified=False,whole_Frame_reassembled=False,
        PE_linked=False,Win32_or_Java_or_JVM_or_Main_executed=False,registered=False,runtime_acceptance_complete=False,game_started=False)
    file=output/'verification.json';write(file,proof);return file


def build(args):
    check(args.assembler.is_file(),'Explicit installed assembler required')
    binding={name:artifact(path) for name,path in (
        ('state',args.state),('source_selection',args.source),('parent_overlay',args.parent),('pinned_C',args.pinned_c),('slot_ABI',args.slot_abi))}
    before_producers=producers()
    metadata=N.bind(args.state,args.source,args.parent,args.pinned_c,args.slot_abi)
    inputs=list(metadata['inputs'])+list(before_producers.values())+[artifact(args.assembler)]
    state=read(args.state)
    inputs += [artifact(ROOT/name) for name in state['tool_sources']]
    output=fresh(args.output);units=assemble(output,args.assembler.resolve(),sources(metadata))
    roots=physical(units,metadata)
    for row in inputs:checked(row)
    check(before_producers==producers(),'Current producers changed during assembly')
    candidate=output/'candidate.json'
    write(candidate,dict(schema=1,family='source-windows-nio-file-attributes-candidate',producers=before_producers,
        binding_inputs=binding,metadata=metadata,units=units,assembler=artifact(args.assembler),physical_roots=roots,inputs=inputs,
        registered=False,linked=False,executed=False,game_started=False,runtime_acceptance_complete=False))
    proof=verify(candidate,output/'canonical')
    write(output/'verification.json',read(proof))
    print(json.dumps(dict(candidate=artifact(candidate),verification=artifact(output/'verification.json')),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='action',required=True)
    make=commands.add_parser('build')
    for name in ('state','source','parent','pinned-c','slot-abi','assembler','output'):
        make.add_argument('--'+name,type=Path,required=True)
    test=commands.add_parser('verify');test.add_argument('--candidate',type=Path,required=True);test.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='build':build(args)
    else:print(json.dumps(artifact(verify(args.candidate,args.output)),indent=2))


if __name__=='__main__':main()
