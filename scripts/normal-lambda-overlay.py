"""Isolated sparse metadata overlay; preserves original IDs and Java functions.

This is a derived experiment, not a production batch verification receipt.
Only declared data ranges and the exact original indy diagnostic are replaced.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lambda_overlay_source',ROOT/'scripts/normal-lambda-source.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
S=C.S;A=C.module('verify-batch-assembly');J=C.module('verify-batch-classes')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def replace(text,before,after,changes,label):
    S.check(text.count(before)==1,'Unique exact source range required: '+label)
    start=text.index(before);end=start+len(before)
    changes.append(dict(label=label,before_sha256=sha(before.encode()),after_sha256=sha(after.encode()),
        original_start=start,original_end=end,prefix_sha256=sha(text[:start].encode()),suffix_sha256=sha(text[end:].encode())))
    return text[:start]+after+text[end:]


def append_extern(text,names):
    old=set(re.findall(r'(?m)^EXTERN (boom_\w+):',text))
    return ''.join('EXTERN '+n+(':'+'PROC' if re.fullmatch(r'boom_m\d+',n) else ':BYTE')+'\n' for n in sorted(names-old))+text


def table_body(table):
    ident=table['id'];ptr='0' if table['array_target'] is None else 'OFFSET boom_m'+str(table['array_target'])
    out=[f'.const\nALIGN 8\nPUBLIC boom_batch_vtable{ident}\nboom_batch_vtable{ident} DWORD 056445350h,1,{len(table["rows"])},0\n'
        f' QWORD OFFSET boom_batch_vrows{ident},{ptr}\n DWORD {table["array_error"]},0\nboom_batch_vrows{ident} LABEL BYTE\n']
    for row in table['rows']:
        ptr='0' if row['target'] is None else 'OFFSET boom_m'+str(row['target'])
        out.append(f' DWORD {row["receiver"]},{row["error"]}\n QWORD {ptr}\n')
    return ''.join(out)


def method_inventory(sources,owners):
    result={}
    for ident in sorted(owners):
        cls=sources.classes[ident]
        for method,raw in zip(cls['method_ids'],sources.raw(cls).methods):
            result[method]=dict(class_id=ident,method=method,**raw)
    return result


def dispatch_overlay(closure,manifest,sources,text,changes):
    # Tables are shared by resolved method, while each unchanged call adapter
    # separately enforces its symbolic-owner and receiver constraints.
    owner_by_method={method:cls['id'] for cls in sources.classes for method in cls['method_ids']}
    owners={a for g in manifest['generated'] for a in g['type']['ancestors']}
    inventory=method_inventory(sources,owners);changed=[]
    for key,old in sorted(closure['selected_dispatch_tables'].items(),key=lambda p:int(p[0])):
        if owner_by_method[old['resolved_method']] not in owners:continue
        new=copy.deepcopy(old);resolved=inventory[old['resolved_method']]
        for g in manifest['generated']:
            if resolved['class_id'] not in g['type']['ancestors']:continue
            signature=resolved['name'],resolved['descriptor']
            sam=g['methods'][-1]
            if signature==(sam['name'],sam['descriptor']):target=sam['id'];error=0
            else:
                declarations=[m for m in inventory.values() if m['class_id'] in g['type']['ancestors'] and
                    (m['name'],m['descriptor'])==signature and not m['access']&(8|2)]
                ordinary=[m for m in declarations if sources.types[m['class_id']]['kind']==1]
                defaults=[m for m in declarations if not m['access']&0x400 and sources.types[m['class_id']]['kind']==2]
                if ordinary:target=ordinary[0]['method'];error=0
                else:
                    most=[m for m in defaults if not any(m['class_id'] in sources.types[n['class_id']]['ancestors'] for n in defaults)]
                    target=most[0]['method'] if len(most)==1 else None
                    error=0 if target is not None else 14 if not most else 15
            new['rows'].append(dict(receiver=g['class_id'],target=target,error=error))
        if new['rows']==old['rows']:continue
        S.check(all(a['receiver']<b['receiver'] for a,b in zip(new['rows'],new['rows'][1:])),
            'Derived dispatch receiver IDs must remain strictly increasing')
        before,after=table_body(old),table_body(new)
        S.check(sha(before.encode())==closure['selected_dispatch_data_sha256']['boom_batch_vtable'+key],
            'Original selected dispatch table seal differs')
        # Parallel data canonicalization moves PUBLIC declarations to its
        # header. Prove the original full body above, then replace the exact
        # canonical data body without moving any other header declaration.
        before=before.replace(f'PUBLIC boom_batch_vtable{key}\n','')
        after=after.replace(f'PUBLIC boom_batch_vtable{key}\n','')
        text=replace(text,before,after,changes,'dispatch:'+key)
        changed.append(dict(id=old['id'],resolved_method=old['resolved_method'],original_rows=len(old['rows']),
            original_body_sha256=sha(before.encode()),derived_body_sha256=sha(after.encode()),
            appended_rows=new['rows'][len(old['rows']):]))
    S.check(changed,'No actual selected dispatch table accepts a generated receiver')
    new_methods={f'boom_m{row["target"]}' for pair in changed for row in pair['appended_rows'] if row['target'] is not None}
    return append_extern(text,new_methods),changed


def recipes(manifest_file,selection):
    V=C.module('verify-normal-lambda-expansion');source_proof=V.verify(manifest_file)
    S.check(source_proof==S.read(manifest_file.with_name('source-verification.json')),'Independent lambda source proof changed')
    manifest=S.read(manifest_file);sources=C.Sources(Path(manifest['base']['batch']),Path(manifest['base']['plan']))
    closure_file=selection/'closure.json';closure=S.read(closure_file);proof_file=selection/'selection-verification.json';proof=S.read(proof_file)
    S.check(proof['verified'] and proof['closure_manifest_sha256']==S.digest(closure_file)['sha256'] and
        closure['source_batch_summary_sha256']==manifest['base']['batch_summary']['digest']['sha256'],
        'Historical full original-source selection identity differs')
    units=proof['verified_assembly_objects']['units'];summary=sources.summary;generated=manifest['generated'];n=len(generated)
    S.check(n>0,'Nonempty lambda expansion required');oldcap=manifest['original_ranges']['types'];newcap=oldcap+n
    S.check(all(not g['layout']['fields'] for g in generated),
        'Capturing source/ASM plans are valid, but this prototype sparse UFMP overlay currently requires no fields')
    plans=[]
    def unit(role,record,text,changes,detail):
        plans.append(dict(role=role,original_assembly=S.artifact(S.checked(record['assembly'])),
            replaced_object=S.artifact(S.checked(record['object'])),text=text,changes=changes,detail=detail))
    # Runtime globals: all old descriptor/field pointer entries are untouched.
    meta=summary['runtime_metadata'];records=meta['units']
    [global_unit]=[u for u in records if 'boom_runtime_type_map DWORD' in S.checked(u['assembly']).read_text()]
    text=S.checked(global_unit['assembly']).read_text();changes=[]
    old=f'boom_runtime_type_map DWORD 052545950h,2,{meta["runtime_rows"]},{oldcap}'
    text=replace(text,old,f'boom_runtime_type_map DWORD 052545950h,2,{meta["runtime_rows"]+n},{newcap}',changes,'runtime:counts')
    anchor='PUBLIC boom_batch_field_records\nboom_batch_field_records LABEL QWORD\n'
    text=replace(text,anchor,''.join(f' QWORD OFFSET boom_t{g["type_id"]}\n' for g in generated)+anchor,changes,'runtime:type-tail')
    fields=[field for g in generated for field in g['layout']['fields']]
    if fields:
        anchor='.data?\nALIGN 8\nboom_batch_runtime_slots'
        text=replace(text,anchor,''.join(f' QWORD OFFSET boom_batch_field_record{f["id"]}\n' for f in fields)+anchor,changes,'runtime:field-tail')
    text=append_extern(text,{f'boom_t{g["type_id"]}' for g in generated}|{f'boom_batch_field_record{f["id"]}' for f in fields})
    unit('runtime-globals',global_unit,text,changes,dict(type_capacity=newcap,old_type_entries_preserved=oldcap,old_fields_preserved=True))
    [row_unit]=[u for u in records if 'boom_batch_runtime_rows LABEL BYTE' in S.checked(u['assembly']).read_text()]
    text=S.checked(row_unit['assembly']).read_text();changes=[]
    extra=''.join(f' QWORD OFFSET boom_layout{g["type_id"]},OFFSET boom_t{g["type_id"]}\n DWORD {g["type_id"]},0\n'
        f' QWORD {g["layout"]["payload_bytes"]}\n DWORD {g["layout"]["reference_prefix"]},0\n' for g in generated)
    text=replace(text,'\n\nEND',extra+'\n\nEND',changes,'runtime:row-tail')
    text=append_extern(text,{f'boom_{prefix}{g["type_id"]}' for g in generated for prefix in ('layout','t')})
    unit('runtime-rows',row_unit,text,changes,dict(appended_rows=n,old_rows_byte_preserved=True))
    # JCLS records/root span and names are reconstructed from the original
    # verified shape, then required to match the complete original source range.
    cls=summary['class_literals'];shape=cls['source_shape']
    with C.zipfile.ZipFile(S.checked(cls['index'])) as archive:
        def rows(name):return [C.json.loads(line) for line in archive.open(name)]
        mirrors={r['type_id']:r for r in rows('types.jsonl')};names=rows('names.jsonl');canonical=rows('canonical_names.jsonl')
    old=J.pool_body(shape,oldcap,cls['loader_keys'],cls['modules'],mirrors,cls['reverse_slots'])
    old+=J.names_body(shape,oldcap,summary['string_literals']['source_layout'],names,canonical)
    mirror_tail={g['type_id']:g['class_mirror'] for g in generated};mirrors.update(mirror_tail)
    for g in generated:
        encoded=g['runtime_class_name'].encode('utf-16-le');utf16=[int.from_bytes(encoded[i:i+2],'little') for i in range(0,len(encoded),2)]
        existing=next((r['id'] for r in canonical if r['utf16']==utf16),None)
        if existing is None:
            existing=len(canonical);hash_=0
            for v in utf16:hash_=(31*hash_+v)&0xffffffff
            canonical.append(dict(id=existing,utf16=utf16,java_hash=hash_,literal=None))
        names.append(dict(type_id=g['type_id'],canonical=existing))
    new=J.pool_body(shape,newcap,cls['loader_keys'],cls['modules'],mirrors,cls['reverse_slots'])
    new+=J.names_body(shape,newcap,summary['string_literals']['source_layout'],names,canonical)
    [class_unit]=cls['units'];text=S.checked(class_unit['assembly']).read_text();changes=[]
    text=replace(text,old,new,changes,'Class:pool-names');text=append_extern(text,{f'boom_t{g["type_id"]}' for g in generated})
    unit('Class-identities-and-names',class_unit,text,changes,dict(type_capacity=newcap,
        root_cells=newcap+len(cls['loader_keys'])+len(cls['modules']),names_roots=len(canonical)*2,
        original_modules_unchanged=True,canonical_names_tail_only=True,hidden_module_loader_rows=mirror_tail))
    # All consumers that seal the normal type capacity must advance together.
    # New non-array classes have zero array scale and no declared source fields.
    unsafe=summary['unsafe_bootstrap'];[record]=unsafe['units'];U=C.module('verify-batch-unsafe')
    with C.zipfile.ZipFile(S.checked(unsafe['index'])) as archive:
        scales=C.json.loads(archive.read('scales.json'));methods=[C.json.loads(line) for line in archive.open('methods.jsonl')]
    S.check(len(scales)==oldcap,'Original Unsafe array-scale capacity differs')
    before=U.data(unsafe['class_id'],unsafe['constants_class_id'],scales,methods)
    after=U.data(unsafe['class_id'],unsafe['constants_class_id'],scales+[0]*n,methods)
    text=S.checked(record['assembly']).read_text();changes=[];text=replace(text,before,after,changes,'Unsafe:scale-pool-tail')
    unit('Unsafe-array-scales',record,text,changes,dict(type_capacity=newcap,new_nonarray_scales=[0]*n,original_scales_preserved=True))
    fields=summary['unsafe_fields']
    with C.zipfile.ZipFile(S.checked(fields['index'])) as archive:ranges=C.json.loads(archive.read('ranges.json'))
    S.check(len(ranges)==oldcap,'Original UFMP class ranges differ')
    range_source='.const\nALIGN 8\nPUBLIC boom_java_unsafe_field_ranges\nboom_java_unsafe_field_ranges LABEL DWORD\n'+''.join(
        f' DWORD {a},{b}\n' for a,b in ranges)
    [record]=[u for u in fields['units'] if 'boom_java_unsafe_field_ranges LABEL DWORD' in S.checked(u['assembly']).read_text()]
    text=S.checked(record['assembly']).read_text();changes=[]
    text=replace(text,range_source,range_source+(' DWORD 0,0\n'*n),changes,'UFMP:class-range-tail')
    unit('Unsafe-field-class-ranges',record,text,changes,dict(type_capacity=newcap,new_class_fields=0,original_declarations_preserved=True))
    [record]=[u for u in fields['units'] if 'boom_java_unsafe_field_pool DWORD' in S.checked(u['assembly']).read_text()]
    text=S.checked(record['assembly']).read_text();changes=[]
    before=f'boom_java_unsafe_field_pool DWORD 055464D50h,2,{oldcap},{manifest["original_ranges"]["fields"]}'
    after=f'boom_java_unsafe_field_pool DWORD 055464D50h,2,{newcap},{manifest["original_ranges"]["fields"]}'
    text=replace(text,before,after,changes,'UFMP:pool-capacity')
    unit('Unsafe-field-pool',record,text,changes,dict(type_capacity=newcap,field_capacity_unchanged=True))
    lookup=summary['class_lookup'];record=lookup['units'][0];text=S.checked(record['assembly']).read_text();changes=[]
    before=f'boom_java_class_lookup_pool DWORD 04A43464Eh,1,{oldcap},'
    text=replace(text,before,f'boom_java_class_lookup_pool DWORD 04A43464Eh,1,{newcap},',changes,'ClassLookup:type-capacity')
    unit('Class-forName-capacity',record,text,changes,dict(type_capacity=newcap,original_lookup_names_unchanged=True,
        generated_hidden_classes_not_discoverable_by_forName=True))
    # Existing native and original Java rows remain a contiguous unchanged prefix.
    frame=S.read(S.checked(closure['runtime_frame_overlay']['reference']['manifest']))
    record=dict(assembly=frame['assembly'],object=frame['object']);text=S.checked(record['assembly']).read_text();changes=[]
    oldcount=len(re.findall(r'(?m)^boom_trace_method\d+ DWORD',text));methods=[m for g in generated for m in g['methods']]
    anchor='.data\nALIGN 8\nPUBLIC boom_trace_pool\n'
    extra=''.join(f'PUBLIC boom_trace_method{m["id"]}\nboom_trace_method{m["id"]} DWORD {m["id"]},{m["frame_flags"]}\n'
        f' QWORD OFFSET boom_t{m["class_id"]}\n DWORD {m["code_length"]},{m["class_id"]}\n QWORD 0\n' for m in methods)
    text=replace(text,anchor,extra+anchor,changes,'frames:row-tail')
    text=replace(text,f' DWORD {oldcount},0\n QWORD OFFSET boom_trace_methods,0,0',
        f' DWORD {oldcount+len(methods)},0\n QWORD OFFSET boom_trace_methods,0,0',changes,'frames:count')
    text=append_extern(text,{f'boom_t{g["type_id"]}' for g in generated})
    unit('contiguous-frames',record,text,changes,dict(original_rows=oldcount,appended_rows=methods,rows_contiguous=True))
    # The parallel data object contains all original class-init descriptors and
    # roots. No source function or descriptor state is rewritten.
    data_units=[u for u in units if re.search(r'(?m)^boom_probe_static_roots LABEL QWORD',S.checked(u['assembly']).read_text())]
    S.check(len(data_units)==1,'One original source data unit required');record=data_units[0]
    text=S.checked(record['assembly']).read_text();changes=[];text,tables=dispatch_overlay(closure,manifest,sources,text,changes)
    start=text.index('boom_java_class_initialization_map LABEL QWORD\n');end=text.index('\n.const',start)
    before=text[start:end];S.check(before.count(' QWORD ')==oldcap,'Original sparse class initializer map capacity differs')
    after=before.rstrip('\n')+'\n'+''.join(f' QWORD OFFSET boom_class{g["class_id"]},0\n' for g in generated)+'\n'
    text=replace(text,before,after,changes,'ClassLookup:initializer-map-tail')
    text=append_extern(text,{'boom_class'+str(g['class_id']) for g in generated})
    unit('selected-dispatch',record,text,changes,dict(tables=tables,original_Java_functions_changed=False,
        original_static_and_failure_roots_byte_preserved=True))
    # The only removed procedure is the existing category3 indy contract; the
    # diagnostic row table and every other source byte remain in its complement.
    [record]=[u for u in units if Path(u['assembly']['path']).name=='diagnostic-stops.asm']
    diagnostic=S.read(selection/'diagnostic.json');labels={g['contract']['binding_label'] for g in generated}
    found=[r for r in diagnostic['rows'] if r['symbol'] in labels]
    S.check(len(found)==len(labels) and all(r['category']==3 for r in found),'Exact original indy diagnostics required')
    original=S.checked(record['assembly']).read_bytes();D=C.module('probe-native-provider-prefix')
    text,complement=D.remove_stops(original,found,True,labels)
    unit('indy-stop-complement',record,text.decode(),[],dict(complement=complement,removed=found))
    for g in generated:
        for method in [g['contract']['implementation_member'],g['object_constructor']]:
            actual=closure['selected_methods'].get(str(method['method']))
            S.check(actual and (actual['class_id'],actual['code_sha256'],actual['source_sha256'])==
                (method['class_id'],method['code_sha256'],method['class_sha256']),'Original lambda target not selected')
        S.check(str(g['contract']['bootstrap_member']['class_id']) in {str(c['class_id']) for c in closure['selected_classes']},
            'Original LambdaMetafactory class initializer not selected')
    return plans,dict(base_closure=S.artifact(closure_file),historical_full_source_proof=S.artifact(proof_file),
        original_Java_Code_preserved=True,original_Java_COFF_preserved=True,original_source_ids_preserved=True,
        generated_catalog_entries=[dict(origin=g['origin'],type=g['type'],class_id=g['class_id'],methods=g['methods'],layout=g['layout']) for g in generated])


def prepare(manifest_file,selection,output,assembler):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated sparse overlay directory required')
    plans,source=recipes(manifest_file,selection);output.mkdir(parents=True)
    def assemble(pair):
        index,plan=pair;asm=output/(str(index).zfill(2)+'-'+plan['role']+'.asm');obj=asm.with_suffix('.obj');asm.write_bytes(plan.pop('text').encode())
        with asm.with_suffix('.log').open('wb') as log:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
        exports,imports=A.coff_symbols(obj);old_exports,old_imports=A.coff_symbols(S.checked(plan['replaced_object']))
        labels={g['contract']['binding_label'] for g in S.read(manifest_file)['generated']}
        frame_names={'boom_trace_method'+str(m['id']) for g in S.read(manifest_file)['generated'] for m in g['methods']}
        expected=old_exports-labels if plan['role']=='indy-stop-complement' else old_exports|frame_names if plan['role']=='contiguous-frames' else old_exports
        S.check(exports==expected,
            'Unexpected sparse overlay PUBLIC symbol change: '+plan['role'])
        return dict(**plan,assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
            original_imports=sorted(old_imports))
    with ThreadPoolExecutor(max_workers=6) as executor:units=list(executor.map(assemble,enumerate(plans)))
    proof=dict(schema=1,scope='isolated_sparse_normal_lambda_metadata_candidate_not_production_batch',expansion=S.artifact(manifest_file),
        source=source,assembler=S.artifact(assembler),tool=S.artifact(Path(__file__)),Class_source_helper=S.artifact(ROOT/'scripts/verify-batch-classes.py'),
        units=units,all_actual_COFF_symbols_checked=True,metadata_extension_emitted=True,shared_batch_modified=False,
        production_batch_verification=False,linked=False,executed=False,game_started=False)
    path=output/'overlay.json';S.write(path,proof);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('expansion',type=Path);parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--assembler',type=Path,required=True);args=parser.parse_args()
    print(prepare(args.expansion.resolve(),args.selection.resolve(),args.output,args.assembler.resolve()))
