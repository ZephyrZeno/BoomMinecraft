"""Rebuild sparse source ranges and inspect their actual normal ABI COFF data."""
import argparse
import importlib.util
from pathlib import Path
import struct


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lambda_overlay_verifier_model',ROOT/'scripts/normal-lambda-overlay.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
C=M.C;S=M.S;P=C.module('parallel-diagnostic-assembly-candidate')


def symbol(obj,name,offset=0):
    row=obj.symbols[name];return obj.by_section[row['section']],row['value']+offset


def number(obj,name,offset=0,width=4):
    section,at=symbol(obj,name,offset);raw=section['raw']
    S.check(0<=at and at+width<=len(raw),'Truncated actual ABI cell: '+name)
    return int.from_bytes(raw[at:at+width],'little')


def pointer(obj,name,offset,target):
    section,at=symbol(obj,name,offset);found=[r for r in section['reloc'] if r[0]==at]
    S.check(len(found)==1 and found[0][2]==1,'Actual ABI pointer needs one ADDR64 relocation: '+name)
    actual=obj.index[found[0][1]];addend=int.from_bytes(section['raw'][at:at+8],'little');expected=obj.symbols[target]
    S.check((actual['name']==target and addend==0) or (expected['section']>0 and actual['section']==expected['section'] and
        actual['value']+addend==expected['value']),'Actual COFF pointer is not the declared symbol: '+name)


def root_span(obj,base,count_name,cells):
    section,start=symbol(obj,base)
    S.check(section['name']=='.bss' and start%8==0 and start+8*cells<=section['size'] and
        number(obj,count_name,width=8)==cells,'Actual normal root span/count differs: '+base)
    return dict(base=base,count_symbol=count_name,cells=cells,section=section['name'],offset=start)


def verify(overlay_file):
    record=S.read(overlay_file);S.check(record['tool']==S.artifact(ROOT/'scripts/normal-lambda-overlay.py') and
        record['Class_source_helper']==S.artifact(ROOT/'scripts/verify-batch-classes.py'),'Current sparse source producer changed')
    manifest_file=S.checked(record['expansion']);manifest=S.read(manifest_file)
    selection=Path(record['source']['base_closure']['path']).parent
    plans,source=M.recipes(manifest_file,selection);S.check(source==record['source'],'Reconstructed sparse source identities differ')
    S.check(len(plans)==len(record['units']),'Sparse source unit coverage differs');objects={};code=[]
    for plan,unit in zip(plans,record['units']):
        text=plan.pop('text');plan=C.json.loads(C.json.dumps(plan))
        S.check(all(unit[k]==v for k,v in plan.items()),'Sparse source recipe/detail changed')
        asm=S.checked(unit['assembly']);obj=S.checked(unit['object'])
        S.check(asm.read_bytes()==text.encode() and M.A.coff_symbols(obj)==(set(unit['exports']),set(unit['imports'])),
            'Sparse source range or actual COFF symbol coverage changed: '+unit['role'])
        actual=P.Coff(obj);objects[unit['role']]=actual;original=P.Coff(S.checked(unit['replaced_object']))
        if unit['role']!='indy-stop-complement':
            S.check(set(actual.functions)==set(original.functions) and (actual.text['raw'] if actual.text else b'')==
                (original.text['raw'] if original.text else b''),'An original Java/native/helper instruction changed')
            if actual.text:
                old_reloc=[(o,original.index[i]['name'],kind) for o,i,kind in original.text['reloc']]
                new_reloc=[(o,actual.index[i]['name'],kind) for o,i,kind in actual.text['reloc']]
                S.check(old_reloc==new_reloc,'An original code relocation target changed')
            code.append(dict(role=unit['role'],original_functions=len(actual.functions),text_bytes=len(actual.text['raw']) if actual.text else 0))
    oldcap=manifest['original_ranges']['types'];newcap=manifest['appended_ranges']['types'][1];generated=manifest['generated']
    globals_=objects['runtime-globals'];rows=objects['runtime-rows'];classes=objects['Class-identities-and-names'];frames=objects['contiguous-frames']
    S.check(number(globals_,'boom_runtime_type_map',12)==newcap,'Actual runtime type capacity differs')
    global_rows=number(globals_,'boom_runtime_type_map',8);old_rows=global_rows-len(generated)
    pool=manifest['base']['batch'];summary=S.read(Path(pool)/'summary.json');classmeta=summary['class_literals']
    S.check(old_rows==summary['runtime_metadata']['runtime_rows'],'Actual runtime row prefix count differs')
    root_cells=newcap+len(classmeta['loader_keys'])+len(classmeta['modules']);spans=[]
    S.check(number(classes,'boom_java_class_pool',12)==newcap,'Actual Class capacity differs')
    spans.append(root_span(classes,'boom_java_class_roots','boom_java_class_root_count',root_cells))
    base=classes.symbols['boom_java_class_roots'];loaders=classes.symbols['boom_java_class_loader_roots'];modules=classes.symbols['boom_java_class_module_roots']
    S.check(base['section']==loaders['section']==modules['section'] and loaders['value']==base['value']+newcap*8 and
        modules['value']==loaders['value']+len(classmeta['loader_keys'])*8,'Class/type/loader/module roots are not one contiguous span')
    names_count=classmeta['name_factory']['root_cells']+len(generated)*2
    spans.append(root_span(classes,'boom_java_class_name_roots','boom_java_class_name_root_count',names_count))
    framecount=number(frames,'boom_trace_pool',16);frameold=framecount-3*len(generated)
    for i,g in enumerate(generated):
        tid=g['type_id'];pointer(globals_,'boom_batch_type_descriptors',tid*8,'boom_t'+str(tid))
        at=(old_rows+i)*40;pointer(rows,'boom_batch_runtime_rows',at,'boom_layout'+str(tid));pointer(rows,'boom_batch_runtime_rows',at+8,'boom_t'+str(tid))
        S.check(number(rows,'boom_batch_runtime_rows',at+16)==tid and number(rows,'boom_batch_runtime_rows',at+24,8)==g['layout']['payload_bytes'] and
            number(rows,'boom_batch_runtime_rows',at+32)==g['layout']['reference_prefix'],'Actual appended runtime row layout differs')
        at=tid*48;pointer(classes,'boom_java_class_records',at,'boom_t'+str(tid))
        for offset,key in ((16,'loader'),(20,'module'),(24,'flags'),(28,'raw_access'),(32,'major')):
            S.check(number(classes,'boom_java_class_records',at+offset)==g['class_mirror'][key],'Actual generated Class identity differs: '+key)
        for j,method in enumerate(g['methods']):
            name='boom_trace_method'+str(method['id']);base=frames.symbols['boom_trace_methods'];row=frames.symbols[name]
            S.check(row['section']==base['section'] and row['value']==base['value']+(frameold+3*i+j)*32 and
                number(frames,name)==method['id'] and number(frames,name,4)==method['frame_flags'] and
                number(frames,name,16)==method['code_length'],'Actual generated frame row is outside the contiguous bank')
            pointer(frames,name,8,'boom_t'+str(tid))
    for unit in record['units']:
        if unit['role']!='selected-dispatch':continue
        dispatch=objects[unit['role']]
        for pair in unit['detail']['tables']:
            name='boom_batch_vtable'+str(pair['id']);rows_name='boom_batch_vrows'+str(pair['id'])
            S.check(number(dispatch,name,8)==pair['original_rows']+len(pair['appended_rows']),'Actual dispatch row count differs')
            for index,row in enumerate(pair['appended_rows'],pair['original_rows']):
                S.check(number(dispatch,rows_name,index*16)==row['receiver'] and number(dispatch,rows_name,index*16+4)==row['error'],
                    'Actual synthetic dispatch receiver/error differs')
                if row['target'] is not None:pointer(dispatch,rows_name,index*16+8,'boom_m'+str(row['target']))
    adapter=S.read(manifest_file.with_name('adapter-assembly.json'));S.checked(adapter['assembly']);native=P.Coff(S.checked(adapter['object']))
    S.check(adapter['generator']==S.artifact(ROOT/'scripts/normal-lambda-assembly.py'),'Current lambda ASM generator differs')
    spans.append(root_span(native,'boom_lambda_failure_roots','boom_lambda_failure_root_count',len(generated)))
    unwind=P.unwind(native);expected={'boom_lambda_initialize'+str(g['type_id']) for g in generated}|{
        'boom_m'+str(m['id'])+'_body' for g in generated for m in g['methods']}
    S.check(set(unwind)==expected,'Actual generated ctor/factory/SAM/frame unwind coverage differs')
    for i,g in enumerate(generated):
        name='boom_class'+str(g['type_id']);root='boom_lambda_failure_root'+str(g['type_id'])
        S.check(number(native,name,8)==0 and number(native,name,24)==g['type_id'] and
            native.symbols[root]['value']==native.symbols['boom_lambda_failure_roots']['value']+8*i,
            'Generated class was initialized by host or its source failure root moved')
        pointer(native,name,16,'boom_lambda_initialize'+str(g['type_id']));pointer(native,name,56,root)
    return dict(schema=1,verified=True,scope='isolated_sparse_lambda_source_ranges_actual_COFF_data_and_unwind',overlay=S.artifact(overlay_file),
        generated_classes=len(generated),original_code_relocation_preservation=code,actual_static_root_spans=spans,
        actual_contiguous_frames=True,actual_synthetic_dispatch_rows=True,actual_runtime_type_rows=True,
        generated_failure_roots_cold=True,original_Java_bytecode_unchanged=True,shared_batch_modified=False,
        production_batch_verification=False,linked=False,executed=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('overlay',type=Path);args=parser.parse_args()
    proof=verify(args.overlay.resolve());path=args.overlay.with_name('verification.json');S.write(path,proof);print(path)
