"""Prove selected initialization bodies/descriptors are unchanged bulk outputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

def check(value,message):
    if not value:raise ValueError(message)

def verify(directory,allow_diagnostics=False):
    directory=Path(directory);manifest_bytes=(directory/'closure.json').read_bytes();manifest=json.loads(manifest_bytes)
    diagnostic=manifest.get('diagnostic_only',False)
    diagnostic_bytes=(directory/'diagnostic.json').read_bytes() if diagnostic else None
    check(allow_diagnostics or not diagnostic and not (directory/'diagnostic-stops.asm').exists(),
          'Diagnostic fail-stop image is not a complete source closure')
    batch=Path(manifest['batch']);summary=json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    plan=Path(manifest['plan']);plan_summary=json.loads((plan/'summary.json').read_text(encoding='utf-8'))
    spec=importlib.util.spec_from_file_location('selected_coff_verifier',Path(__file__).with_name('verify-batch-assembly.py'))
    coff=importlib.util.module_from_spec(spec);spec.loader.exec_module(coff)
    spec=importlib.util.spec_from_file_location('selected_batch_artifacts',Path(__file__).with_name('closure-batch-artifacts.py'))
    artifacts=importlib.util.module_from_spec(spec);spec.loader.exec_module(artifacts)
    artifacts.configure(coff,batch,summary,plan)
    source_artifacts={};checked_sources=set()
    def collect_source_units(value):
        if isinstance(value,dict):
            record=value.get('assembly')
            if isinstance(record,dict) and 'path' in record and 'digest' in record:source_artifacts[str(Path(record['path']).resolve())]=record
            for child in value.values():collect_source_units(child)
        elif isinstance(value,list):
            for child in value:collect_source_units(child)
    collect_source_units(summary)
    def check_source_unit(path):
        key=str(Path(path).resolve())
        if key in checked_sources:return
        check(key in source_artifacts,'Selected original assembly is not in the base batch')
        record=source_artifacts[key]
        with Path(path).open('rb') as stream:h=hashlib.file_digest(stream,'sha256').hexdigest()
        check(Path(path).stat().st_size==record['digest']['size'] and h==record['digest']['sha256'],'Selected original assembly artifact changed')
        checked_sources.add(key)
    check(summary['input_fingerprint']==plan_summary['input_fingerprint'],'Selected batch/plan source identity differs')
    if 'source_input_fingerprint' in manifest:
        with (plan/'classes.jsonl').open('rb') as stream:classes_sha=hashlib.file_digest(stream,'sha256').hexdigest()
        check(manifest['source_input_fingerprint']==summary['input_fingerprint'] and manifest['batch_ir_identity']==summary['ir_identity']
              and classes_sha==manifest['source_classes_sha256']==plan_summary['artifacts']['classes']['digest']['sha256'],'Selected source plan or IR identity changed')
    with zipfile.ZipFile(coff.artifact(batch,summary['class_state']['index'],'class-state')) as bundle:
        classes={s['class_id']:s for s in map(json.loads,bundle.read('classes.jsonl').splitlines())}
    selected={s['class_id']:s for s in manifest['selected_classes']}
    contracts=manifest.get('selected_array_clone_contracts',{})
    sites=manifest.get('selected_dispatch_sites',{});tables=manifest.get('selected_dispatch_tables',{})
    concat_sites=manifest.get('selected_String_concat_sites',{})
    if concat_sites:
        with zipfile.ZipFile(coff.artifact(batch,summary['string_concat']['index'],'string-concat')) as bundle:
            original={r['label']:r for r in map(json.loads,bundle.read('sites.jsonl').splitlines()) if r['label'] in concat_sites}
        check(concat_sites==original and all(r['plan'] is not None and r['diagnostic'] is None for r in original.values()),'Selected concat source plan differs')
    if sites or tables:
        check(not manifest.get('dispatch_rows_pruned',False),'Source closure silently pruned receiver rows')
        check({str(s['table']) for s in sites.values()}==set(tables),'Selected dispatch site/table coverage differs')
        with zipfile.ZipFile(coff.artifact(batch,summary['dispatch']['index'],'dispatch')) as bundle:
            original_sites={row['label']:row for line in bundle.open('sites.jsonl') if (row:=json.loads(line))['label'] in sites}
            original_tables={str(row['id']):row for line in bundle.open('tables.jsonl') if str((row:=json.loads(line))['id']) in tables}
        check(sites==original_sites and tables==original_tables,'Selected dispatch plan differs from bulk source')
        check(all(s['diagnostic'] is None for s in sites.values()) and all(t['diagnostic'] is None for t in tables.values()),'Selected unavailable dispatch contract')
    if contracts:
        with zipfile.ZipFile(coff.artifact(batch,summary['array_clone']['index'],'array-clone')) as bundle:
            clone_sites={s['label']:s for s in map(json.loads,bundle.read('sites.jsonl').splitlines())}
        check(all(clone_sites.get(label)==row for label,row in contracts.items()),'Selected array clone contract differs from bulk source')
    check(all(classes[id_]==state and not state['diagnostic'] for id_,state in selected.items()),'Selected class source plan differs')
    spec=importlib.util.spec_from_file_location('verified_initialization_sources',Path(__file__).with_name('batch-source.py'))
    source_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(source_module)
    sources=source_module.Sources();text=sources.text
    closure_path=directory/'initialization-closure.asm';closure_sources=source_module.Sources()
    assembly=closure_path.read_text(encoding='utf-8');assembly_spans=source_module.procedure_spans(assembly);expected_functions={};handler_paths={}
    class_results={}
    for shard in summary['shards']:
        needed={m['class_id'] for m in manifest['selected_methods'].values()}-set(class_results)
        if not needed:break
        with zipfile.ZipFile(coff.artifact(batch,shard['zip'],'shards')) as bundle:
            entries=set(bundle.namelist())
            for id_ in needed:
                name=f'classes/{id_:06}.json'
                if name in entries:class_results[id_]=(json.loads(bundle.read(name)),shard)
    for symbol in manifest['selected_function_sha256']:
        match=re.fullmatch(r'boom_m(\d+)(?:_body)?',symbol)
        if match:
            id_=int(match[1]);evidence=manifest['selected_methods'][str(id_)]
            unit,shard=class_results[evidence['class_id']];method=next(m for m in unit['methods'] if m['id']==id_)
            check(method['assembly_emitted'] and (method['name'],method['descriptor'],method['code_sha256'],unit['source_sha256'])==
                  (evidence['name'],evidence['descriptor'],evidence['code_sha256'],evidence['source_sha256']),'Selected Java method provenance differs')
            path=shard['units'][method['assembly_unit']]['assembly']['path']
        elif symbol in concat_sites:
            path=summary['string_concat']['units'][concat_sites[symbol]['assembly_unit']]['assembly']['path']
        elif symbol in contracts:
            path=summary['array_clone']['units'][contracts[symbol]['assembly_unit']]['assembly']['path']
        elif symbol in sites:
            path=summary['dispatch']['units'][sites[symbol]['assembly_unit']]['assembly']['path']
        elif symbol=='boom_batch_virtual_invoke' and sites:
            path=summary['dispatch']['units'][0]['assembly']['path']
        else:
            match=re.fullmatch(r'boom_batch_initialize_(\d+)',symbol)
            check(match is not None and int(match[1]) in selected,'Unknown generated closure function')
            path=summary['class_state']['units'][selected[int(match[1])]['assembly_unit']]['assembly']['path']
        check_source_unit(path)
        body=sources.function(path,symbol);expected_functions[symbol]=body
        for id_ in map(int,re.findall(r'\bboom_handlers(\d+)\b',body)):handler_paths[id_]=path
        check(hashlib.sha256(body.encode()).hexdigest()==manifest['selected_function_sha256'][symbol]
              and symbol in assembly_spans and assembly[slice(*assembly_spans[symbol])]==body,'Selected source function was changed')
    actual_functions=set(re.findall(r'(?m)^(boom_\w+) PROC\b',assembly))
    check(actual_functions==set(expected_functions),'Closure contains added/removed function bodies')
    check(set(manifest.get('selected_handler_data_sha256',{}))==set(map(str,handler_paths)), 'Selected exception handler data coverage differs')
    for id_,path in handler_paths.items():
        data=sources.handler_table(path,id_)
        check(closure_sources.handler_table(closure_path,id_)==data and hashlib.sha256(data.encode()).hexdigest()==manifest['selected_handler_data_sha256'][str(id_)],
              'Selected exception handler data changed')
    check(set(map(int,re.findall(r'(?m)^boom_handlers(\d+) DWORD',assembly)))==set(handler_paths),'Closure contains extra exception handler tables')
    if concat_sites:
        spec=importlib.util.spec_from_file_location('closure_concat_source',Path(__file__).with_name('verify-batch-concat.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        c=summary['string_concat']
        for label,row in concat_sites.items():
            data=module.body(label,row['plan'],c['bootstrap']['class_id'],c['source_layout']).partition('.code\n')[0]
            path=c['units'][row['assembly_unit']]['assembly']['path']
            check(sources.fragment(path,label,data)==data and closure_sources.fragment(closure_path,label,data)==data and
                  hashlib.sha256(data.encode()).hexdigest()==manifest['selected_concat_data_sha256'][label],'Selected concat data changed')
    expected_dispatch_data={}
    for id_,table in tables.items():
        ptr='0' if table['array_target'] is None else f"OFFSET boom_m{table['array_target']}"
        rows=[f".const\nALIGN 8\nPUBLIC boom_batch_vtable{id_}\nboom_batch_vtable{id_} DWORD 056445350h,1,{len(table['rows'])},0\n QWORD OFFSET boom_batch_vrows{id_},{ptr}\n DWORD {table['array_error']},0\nboom_batch_vrows{id_} LABEL BYTE\n"]
        for row in table['rows']:
            ptr='0' if row['target'] is None else f"OFFSET boom_m{row['target']}"
            rows.append(f" DWORD {row['receiver']},{row['error']}\n QWORD {ptr}\n")
        expected_dispatch_data['boom_batch_vtable'+id_]=(''.join(rows),table)
    for label,site in sites.items():
        d=site['dispatch'];body=f".const\nALIGN 8\nboom_batch_vconstraints_{label} QWORD OFFSET boom_t{d['symbolic_owner']},OFFSET boom_t{d['receiver_constraint']}\n"
        expected_dispatch_data['boom_batch_vconstraints_'+label]=(body,site)
    check(set(expected_dispatch_data)==set(manifest.get('selected_dispatch_data_sha256',{})),'Selected dispatch data coverage differs')
    for name,(body,row) in expected_dispatch_data.items():
        path=summary['dispatch']['units'][row['assembly_unit']]['assembly']['path']
        check_source_unit(path)
        check(sources.fragment(path,name,body)==body and closure_sources.fragment(closure_path,name,body)==body and
              hashlib.sha256(body.encode()).hexdigest()==manifest['selected_dispatch_data_sha256'][name],
              'Selected dispatch data was changed')
    check(set(re.findall(r'(?m)^(boom_batch_vtable\d+) DWORD',assembly))=={'boom_batch_vtable'+id_ for id_ in tables}
          and set(re.findall(r'(?m)^boom_batch_vrows(\d+) LABEL',assembly))==set(tables)
          and set(re.findall(r'(?m)^(boom_batch_vconstraints_\w+) QWORD',assembly))=={'boom_batch_vconstraints_'+label for label in sites},'Closure has extra dispatch data')
    if contracts:
        source=text(summary['array_clone']['units'][summary['array_clone']['contract']['pool_unit']]['assembly']['path'])
        pattern=r'(?m)^boom_batch_array_clone_pool DWORD 041434C50h,1\n QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,0\n'
        original=re.search(pattern,source);copy=re.search(pattern,assembly)
        check(original is not None and copy is not None and copy[0]==original[0] and
              hashlib.sha256(copy[0].encode()).hexdigest()==manifest['selected_array_clone_pool_sha256'],'Selected array clone pool was changed')
    expected_fields=set();expected_roots='boom_probe_static_roots LABEL QWORD\n';root_cells=0
    for id_,state in sorted(selected.items()):
        for f in state['fields']:
            expected_fields.add(f"boom_s{id_}_{f['index']}")
            if f['reference']:
                expected_roots+=f"PUBLIC boom_s{id_}_{f['index']}\nboom_s{id_}_{f['index']} QWORD ?\n";root_cells+=1
        expected_roots+=f'boom_batch_class_failure_root{id_} QWORD ?\n';root_cells+=1
        path=summary['class_state']['units'][state['assembly_unit']]['assembly']['path']
        check_source_unit(path)
        check(sources.class_descriptor(path,id_)==closure_sources.class_descriptor(closure_path,id_),'Selected class descriptor was changed')
    check(expected_roots in assembly and f'boom_probe_static_root_count QWORD {root_cells}' in assembly,'Selected root region differs')
    check(set(re.findall(r'(?m)^(boom_s\d+_\d+) QWORD \?$',assembly))==expected_fields,'Selected static cells differ')
    native_exports=set();frame_exports=set();selected_native=manifest.get('selected_native_methods',{})
    if summary['schema']>=23:
        check(manifest.get('source_frame_abi')==3,'Selected source frame ABI missing')
        module=summary['frames'];data=module['units'][0]
        coff.artifact(batch,data['assembly'],'frames');defs,_=coff.coff_symbols(coff.artifact(batch,data['object'],'frames'));frame_exports.update(defs)
        check({'boom_trace_pool','boom_trace_methods','boom_release_trace_pool'}<=defs,'Selected frame data exports missing')
        linked_frame=manifest.get('runtime_frame_overlay',{}).get('object',data['object'])
        check(linked_frame['path'] in manifest['objects'],'Selected image omitted Java frame data')
        caller=manifest.get('selected_caller_natives',{})
        if caller:
            with zipfile.ZipFile(coff.artifact(batch,module['index'],'frames')) as z:natives={str(r['method']):r for r in map(json.loads,z.read('natives.jsonl').splitlines())}
            check(all(natives.get(i)==r and r['class_id'] in selected for i,r in caller.items()),'Selected caller native source differs')
            unit=module['units'][1];coff.artifact(batch,unit['assembly'],'frames');d,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'frames'))
            check(d=={'boom_java_caller_pool'}|{f"boom_m{r['method']}{suffix}" for r in natives.values() for suffix in ('','_native')},'Selected caller COFF differs')
            check(unit['object']['path'] in manifest['objects'],'Selected image omitted caller native object');frame_exports.update(d)
    if selected_native:
        native_summary=summary['system_natives']
        with zipfile.ZipFile(coff.artifact(batch,native_summary['index'],'system-natives')) as bundle:
            originals={str(m['method']):m for m in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(originals.get(id_)==record for id_,record in selected_native.items()),'Selected native declaration differs from source implementation')
        check(native_summary['class_id'] in selected,'Native envelope omitted declaring class state')
        expected_native={f"boom_m{m['method']}{suffix}" for m in originals.values() for suffix in ('','_native')}|{'boom_batch_system_native_pool','boom_batch_system_native_table'}
        if native_summary['abi']>=2:expected_native.update(('boom_batch_system_stream_pool','boom_batch_system_stream_rows'))
        for unit in native_summary['units']:
            coff.artifact(batch,unit['assembly'],'system-natives')
            native_defs,native_imports=coff.coff_symbols(coff.artifact(batch,unit['object'],'system-natives'))
            native_exports.update(native_defs)
        check(native_exports==expected_native,'Source native object definitions differ')
    native_exports.update(frame_exports)
    selected_class_sites=manifest.get('selected_Class_literals',{});selected_class_natives=manifest.get('selected_Class_core_natives',{})
    selected_intern_natives=manifest.get('selected_String_intern_natives',{})
    if selected_class_sites or selected_class_natives or selected_intern_natives:
        c=summary['class_literals']
        with zipfile.ZipFile(coff.artifact(batch,c['index'],'class-literals')) as bundle:
            sites_={r['label']:r for r in map(json.loads,bundle.read('sites.jsonl').splitlines())}
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(sites_.get(label)==r and r['diagnostic'] is None for label,r in selected_class_sites.items()) and
              all(methods_.get(id_)==r and r['access']&8==0 for id_,r in selected_class_natives.items()),'Selected Class literal/native provenance differs')
        expected={s['label'] for s in sites_.values() if s['assembly_unit'] is not None}|{f"boom_m{m['method']}{suffix}" for m in methods_.values() for suffix in ('','_native')}|{'boom_java_class_pool','boom_java_class_root_count','boom_java_class_roots','boom_java_class_loader_roots','boom_java_class_module_roots','boom_java_class_records'}
        if summary['schema']>=11:expected.update(('boom_java_class_name_pool','boom_java_class_name_root_count','boom_java_class_name_roots'))
        actual=set()
        for unit in c['units']:
            coff.artifact(batch,unit['assembly'],'class-literals');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'class-literals'));actual.update(defs)
        check(actual==expected,'Source Class module COFF definitions differ');native_exports.update(actual)
    if selected_intern_natives:
        module=summary['string_intern']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'string-intern')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(id_)==r and r['access']==0x101 for id_,r in selected_intern_natives.items()),'Selected String.intern native provenance differs')
        expected={f"boom_m{m['method']}{suffix}" for m in methods_.values() for suffix in ('','_native')}|{'boom_java_string_intern_pool','boom_java_string_intern_root_count','boom_java_string_intern_root'}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'string-intern');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'string-intern'));actual.update(defs)
        check(actual==expected,'Source intern module COFF definitions differ');native_exports.update(actual)
    selected_properties=manifest.get('selected_property_natives',{})
    if selected_properties:
        module=summary['properties']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'properties')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(id_)==r and r['access']==0x10a and r['class_id'] in selected for id_,r in selected_properties.items()),
              'Selected property native provenance/initialization owner differs')
        expected={f"boom_m{m['method']}{suffix}" for m in methods_.values() for suffix in ('','_native')}|{
            'boom_java_properties_roots','boom_java_properties_root_count','boom_java_platform_properties_pool',
            'boom_java_vm_properties_pool','boom_java_properties_string_pool'}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'properties');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'properties'));actual.update(defs)
        check(actual==expected,'Source property module COFF definitions differ');native_exports.update(actual)
    spec=importlib.util.spec_from_file_location('selected_logical_object_provenance',Path(__file__).with_name('diagnostic-objects.py'))
    provenance=importlib.util.module_from_spec(spec);spec.loader.exec_module(provenance)
    defined,undefined=provenance.logical_symbols(directory,'initialization-closure',coff.coff_symbols)
    selected_bootstrap=manifest.get('selected_Class_bootstrap_natives',{})
    if selected_bootstrap:
        module=summary['class_bootstrap']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'class-bootstrap')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(id_)==r and r['access'] in (0x108,0x10a) and r['class_id'] in selected for id_,r in selected_bootstrap.items()),
              'Selected Class bootstrap native source/initialization owner differs')
        expected={f"boom_m{m['method']}{suffix}" for m in methods_.values() for suffix in ('','_native')}|{
            'boom_java_class_bootstrap_pool','boom_java_class_bootstrap_natives','boom_java_primitive_names'}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'class-bootstrap');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'class-bootstrap'));actual.update(defs)
        check(actual==expected,'Class bootstrap module COFF definitions differ');native_exports.update(actual)
    selected_unsafe=manifest.get('selected_Unsafe_natives',{})
    if selected_unsafe:
        module=summary['unsafe_bootstrap']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'unsafe-bootstrap')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(id_)==r and r['class_id'] in selected for id_,r in selected_unsafe.items()),
              'Selected Unsafe native source/initialization owner differs')
        check(module['constants_class_id'] in selected,'UnsafeConstants original source initialization was omitted')
        expected={f"boom_m{m['method']}{suffix}" for m in methods_.values() for suffix in ('','_native')}|{
            'boom_java_unsafe_pool','boom_java_unsafe_bindings','boom_java_unsafe_scales','boom_java_unsafe_constant_cells'}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'unsafe-bootstrap');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'unsafe-bootstrap'));actual.update(defs)
        check(actual==expected,'Unsafe module COFF definitions differ');native_exports.update(actual)
    selected_vm=manifest.get('selected_VM_natives',{})
    if selected_vm:
        module=summary['vm_registration']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'vm-registration')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(i)==r and r['class_id'] in selected for i,r in selected_vm.items()),'Selected VM native source/initializer differs')
        expected={'boom_java_vm_pool'}|{f"boom_m{m['method']}{x}" for m in methods_.values() for x in ('','_native')}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'vm-registration');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'vm-registration'));actual.update(defs)
        check(actual==expected,'Selected VM COFF definitions differ');native_exports.update(actual)
    selected_resources=manifest.get('selected_Runtime_resource_natives',{})
    if selected_resources:
        module=summary['runtime_resources']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'runtime-resources')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(i)==r and r['class_id'] in selected for i,r in selected_resources.items()),'Selected Runtime resource source/initializer differs')
        expected={'boom_java_runtime_pool'}|{f"boom_m{m['method']}{x}" for m in methods_.values() for x in ('','_native')}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'runtime-resources');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'runtime-resources'));actual.update(defs)
        check(actual==expected,'Selected Runtime resource COFF differs');native_exports.update(actual)
    selected_bitcasts=manifest.get('selected_bitcast_natives',{})
    if selected_bitcasts:
        module=summary['bitcasts']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'bitcasts')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(i)==r and r['class_id'] in selected for i,r in selected_bitcasts.items()) and set(module['source_class_ids'])<=set(selected),
              'Selected bitcast declarations/source initializers differ')
        expected={'boom_java_bitcast_pool'}|{f"boom_m{m['method']}{x}" for m in methods_.values() for x in ('','_native')}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'bitcasts');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'bitcasts'));actual.update(defs)
        check(actual==expected,'Selected bitcast COFF definitions differ');native_exports.update(actual)
    selected_unsafe_fields=manifest.get('selected_Unsafe_field_natives',{})
    if selected_unsafe_fields:
        module=summary['unsafe_fields']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'unsafe-fields')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(i)==r and r['class_id'] in selected for i,r in selected_unsafe_fields.items()),
              'Selected Unsafe field native source differs')
        expected={'boom_java_unsafe_field_pool','boom_java_unsafe_field_names','boom_java_unsafe_field_ranges','boom_java_unsafe_field_pages'}
        expected|={f'boom_java_unsafe_field_page{i}' for i in range(module['pages'])}
        expected|={f"boom_m{m['method']}{x}" for m in methods_.values() for x in ('','_native')}
        actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'unsafe-fields');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'unsafe-fields'));actual.update(defs)
        check(actual==expected,'Selected Unsafe field COFF definitions differ');native_exports.update(actual)
    selected_unsafe_memory=manifest.get('selected_Unsafe_memory_natives',{})
    if selected_unsafe_memory:
        module=summary['unsafe_memory']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'unsafe-memory')) as bundle:
            methods_={str(r['method']):r for r in map(json.loads,bundle.read('methods.jsonl').splitlines())}
        check(all(methods_.get(i)==r and r['class_id'] in selected for i,r in selected_unsafe_memory.items()) and selected_unsafe_fields,
              'Selected typed memory declarations/shared field dependency differ')
        expected={f"boom_m{m['method']}{x}" for m in methods_.values() for x in ('','_native')};actual=set()
        for unit in module['units']:
            coff.artifact(batch,unit['assembly'],'unsafe-memory');defs,_=coff.coff_symbols(coff.artifact(batch,unit['object'],'unsafe-memory'));actual.update(defs)
        check(actual==expected,'Selected typed memory COFF definitions differ');native_exports.update(actual)
    selected_lookup=manifest.get('selected_Class_lookup_natives',{})
    if selected_lookup:
        module=summary['class_lookup']
        with zipfile.ZipFile(coff.artifact(batch,module['index'],'class-lookup')) as z:
            lookup_methods={r['method']:r for r in map(json.loads,z.read('methods.jsonl').splitlines())}
            lookup_inits={r['class_id']:r for r in map(json.loads,z.read('initializers.jsonl').splitlines())}
        check(all(lookup_methods.get(int(i))==r for i,r in selected_lookup.items()) and {r['class_id'] for r in lookup_methods.values()}<=set(selected),
              'Selected Class lookup provenance/owners differ')
        check(all(classes[i]['source_sha256']==r['source_sha256'] and not classes[i]['diagnostic'] for i,r in lookup_inits.items()),'Initialization map source identity differs')
        actual,imports=coff.coff_symbols(coff.artifact(batch,module['units'][0]['object'],'class-lookup'))
        expected={'boom_java_class_lookup_pool','boom_java_class_lookup_rows','boom_java_class_lookup_names'}|{f"boom_m{r['method']}{suffix}" for r in lookup_methods.values() for suffix in ('','_native')}
        check(actual==expected,'Selected Class lookup COFF exports differ');native_exports.update(actual)
    required=set(expected_functions)|expected_fields|{f'boom_class{i}' for i in selected}|{'boom_probe_static_roots','boom_probe_static_root_count'}
    all_source_initializer_map=manifest.get('all_source_initializer_map',False)
    if selected_lookup or all_source_initializer_map:
        if all_source_initializer_map:
            with zipfile.ZipFile(coff.artifact(batch,summary['runtime_metadata']['index'],'runtime-metadata')) as z:
                ids={t['id'] for line in z.open('types.jsonl') if (t:=json.loads(line))['kind'] in (1,2) and
                     t['id'] in classes and classes[t['id']]['diagnostic'] is None and t['source_sha256']==classes[t['id']]['source_sha256']}
            check(not selected_lookup or set(lookup_inits)<=ids,'Full mirror map omitted a bootstrap source identity')
        else:ids=set(lookup_inits)
        spec=importlib.util.spec_from_file_location('verified_source_initialization_map',Path(__file__).with_name('verify-batch-class-lookup.py'))
        lookup_model=importlib.util.module_from_spec(spec);spec.loader.exec_module(lookup_model)
        projection=lookup_model.initialization_map(summary['class_lookup']['type_capacity'],ids,set(selected))
        check(projection in assembly,'Selected Class initialization registry changed')
        required.add('boom_java_class_initialization_map')
    if contracts:required.add('boom_batch_array_clone_pool')
    required.update('boom_batch_vtable'+id_ for id_ in tables)
    if manifest.get('constructor_invocation_sites'):required.add('boom_provider_constructor_selected_sites')
    check(defined==required,'Selected COFF definitions differ from verified source bodies/data')
    provider_module=None;packs=[]
    if manifest.get('runtime_provider_packs'):
        spec=importlib.util.spec_from_file_location('closure_separate_native_providers',Path(__file__).with_name('verify-runtime-provider-pack.py'))
        provider_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider_module)
        paths=[str(provider_module.S.checked(p['manifest'])) for p in manifest['runtime_provider_packs']]
        packs=provider_module.load_packs(batch,plan,paths)
        check(provider_module.references(packs)==manifest['runtime_provider_packs'],'Closure provider provenance differs')
    spec=importlib.util.spec_from_file_location('closure_provider_dependency_projection',Path(__file__).with_name('diagnostic-closure.py'))
    provider_projection=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider_projection)
    overlay=provider_projection.frame_overlay(packs)
    check(manifest.get('runtime_frame_overlay')==overlay,'Closure native frame overlay differs')
    if overlay:
        check(provider_projection.same_provider_record(overlay['replaced_data_object'],summary['frames']['units'][0]['object']) and
              manifest['objects'].count(overlay['object']['path'])==1 and
              overlay['replaced_data_object']['path'] not in manifest['objects'],'Closure did not replace exactly the base frame data object')
    site_data,_,_,site_proof=provider_projection.constructor_selection(packs,set(manifest.get('selected_runtime_provider_packs',[])),selected,manifest['selected_methods'])
    check(manifest.get('constructor_invocation_sites')==site_proof and (not site_data or site_data in assembly),'Closure constructor callsite source/data differs')
    if diagnostic:
        spec=importlib.util.spec_from_file_location('verified_diagnostic_stops',Path(__file__).with_name('verify-diagnostic-closure.py'))
        diagnostic_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic_module)
        diagnostics,diagnostic_exports=diagnostic_module.verify_stops(directory,manifest,summary,coff,verified_provider_packs=packs)
        native_exports.update(diagnostic_exports)
    provider_native_count=0
    needs_source_initializer_map=False
    if manifest.get('runtime_provider_packs'):
        members={str(m['method']):(i,m) for i,p in enumerate(packs) for m in p['manifest']['methods']}
        selected_pack_native=manifest.get('selected_runtime_provider_natives',{});indices=set()
        for key,m in selected_pack_native.items():
            check(key in members and members[key][1]==m,'Selected provider native differs from original declaration');indices.add(members[key][0])
        check(sorted(indices)==manifest['selected_runtime_provider_packs'],'Selected provider package set differs')
        for i in sorted(indices):
            p=packs[i]['manifest'];check(set(p['required_class_ids'])<=set(selected),'Provider omitted original class initialization dependencies')
            needs_source_initializer_map|='class_initialization_map' in p['required_base_modules']
            check(all(str(m) in manifest['selected_methods'] for m in p.get('required_java_methods',[])),
                  'Provider omitted required original Java callbacks')
            check(set(p.get('required_source_contracts',[]))<=set(manifest.get('selected_dispatch_sites',{})),
                  'Provider omitted required original dispatch contracts')
            families={packs[j]['manifest']['family'] for j in indices}
            check(set(p.get('required_provider_families',[]))<=families,'Provider omitted required separate native family')
            check(p['object']['path'] in manifest['objects'],'Provider COFF omitted from closure link')
            definitions,imports=coff.coff_symbols(Path(p['object']['path']),set(p.get('allowed_foreign_imports',[])))
            check(not native_exports&definitions,'Provider conflicts with selected base definitions');native_exports.update(definitions)
        provider_native_count=len(selected_pack_native)
    check(all_source_initializer_map is needs_source_initializer_map,'Provider and Class initializer map scope differ')
    for symbol in undefined:
        check(symbol in native_exports or not re.fullmatch(r'boom_m\d+(?:_body)?|boom_class\d+|boom_s\d+_\d+|boom_batch_call_\d+_\d+_\d+',symbol),'Closure omitted a Java/class/call dependency')
    check(closure_path.read_text(encoding='utf-8')==assembly,'Selected assembly changed during independent verification')
    check((directory/'closure.json').read_bytes()==manifest_bytes and
          (not diagnostic or (directory/'diagnostic.json').read_bytes()==diagnostic_bytes),'Source selection changed during independent verification')
    return dict(verified=True,scope=('selected_original_source_with_development_fail_stops_only' if diagnostic else 'selected_original_functions_descriptors_static_cells_and_COFF_only'),
                closure_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                diagnostic_manifest_sha256=hashlib.sha256(diagnostic_bytes).hexdigest() if diagnostic else None,
                diagnostic_only=diagnostic,source_closure_complete=not diagnostic,
                classes=len(selected),Java_methods=len(manifest['selected_methods']),functions=len(expected_functions),root_cells=root_cells,
                original_array_clone_sites=len(contracts),
                original_virtual_sites=len(sites),original_dispatch_tables=len(tables),dispatch_rows_pruned=False,
                source_native_methods=len(selected_native),
                source_Class_literals=len(selected_class_sites),source_Class_core_natives=len(selected_class_natives),
                source_String_intern_natives=len(selected_intern_natives),
                source_property_natives=len(selected_properties),
                source_Class_bootstrap_natives=len(selected_bootstrap),
                source_Unsafe_natives=len(selected_unsafe),
                source_VM_natives=len(selected_vm),
                source_Runtime_resource_natives=len(selected_resources),
                source_bitcast_natives=len(selected_bitcasts),
                source_Unsafe_field_natives=len(selected_unsafe_fields),
                source_Unsafe_memory_natives=len(selected_unsafe_memory),source_Class_lookup_natives=len(selected_lookup),
                source_String_concat_sites=len(concat_sites),
                source_runtime_provider_natives=provider_native_count,
                source_exception_handler_tables=len(handler_paths),
                closure_assembly_sha256=hashlib.sha256(assembly.encode()).hexdigest(),game_started=False,full_game_ready=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=verify(args.directory)
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
