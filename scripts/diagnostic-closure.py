"""Offline development fail-stop image metadata, never a semantic provider."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'native/diagnostic/stop.asm.inc'
CONTEXT_HELPERS=[ROOT/'native/diagnostic/context_map.asm.inc',ROOT/'native/diagnostic/context_stop.asm.inc']
CONTEXT_EXPORTS={'boom_diagnostic_context_map','boom_diagnostic_context_map_record','boom_diagnostic_context_map_row'}
STOP_KIND=0xB001
SYMBOL=re.compile(r'boom_m\d+(?:_body)?|boom_batch_call_\d+_\d+_\d+|boom_batch_literal_load_\d+_\d+|boom_batch_initialize_\d+')
CATEGORIES={'unselected_method':1,'method':2,'virtual_dispatch':3,'invokedynamic':3,
            'literal_resolution':3,'signature_polymorphic_native':3,'call_or_literal_contract':3,'abi_dependency':4,'unselected_initialization':5}


def pe_exports(path):
    data=Path(path).read_bytes()
    check(data[:2]==b'MZ','Not a PE image');pe=struct.unpack_from('<I',data,0x3c)[0]
    check(data[pe:pe+4]==b'PE\0\0','Invalid PE signature')
    machine,count=struct.unpack_from('<HH',data,pe+4);optional=pe+24;size=struct.unpack_from('<H',data,pe+20)[0]
    check(machine==0x8664 and 1<=count<=96 and size>=120 and struct.unpack_from('<H',data,optional)[0]==0x20b,'Unsupported runtime PE format')
    sections=[]
    for i in range(count):
        virtual,raw,offset=struct.unpack_from('<III',data,optional+size+i*40+12);sections.append((virtual,raw,offset))
    def position(rva,needed):
        for start,length,offset in sections:
            if start<=rva and rva+needed<=start+length:
                p=offset+rva-start;check(p+needed<=len(data),'PE data exceeds file');return p
        raise ValueError('PE RVA outside raw sections')
    export_rva=struct.unpack_from('<I',data,optional+112)[0];p=position(export_rva,40)
    names=struct.unpack_from('<I',data,p+24)[0];address=struct.unpack_from('<I',data,p+32)[0]
    check(names<=100000,'PE export count exceeds diagnostic budget');result=set()
    for i in range(names):
        rva=struct.unpack_from('<I',data,position(address+i*4,4))[0];begin=position(rva,1);end=data.find(b'\0',begin,begin+1024)
        check(end>=begin,'Unterminated PE export');result.add(data[begin:end].decode('ascii'))
    return result


def frame_runtime_identity(summary,runtime):
    if summary['schema']<23:return
    runtime=Path(runtime);metadata=json.loads(runtime.with_name('runtime.json').read_text(encoding='utf-8-sig'))
    check(metadata.get('sha256')==hashlib.sha256(runtime.read_bytes()).hexdigest(),'Frame runtime DLL differs from its build metadata')
    check(all(metadata.get(k) is False for k in ('java_runtime','rust_runtime','c_runtime')),'Frame runtime must use the assembly runtime')
    check(all(metadata.get('sources',{}).get(p)==h for p,h in summary['frames']['kernel_sha256'].items()),
          'Source frame/runtime kernel ABI differs; use the runtime built with this batch')


def checked_provider_record(record):
    path=Path(record['path'])
    check(path.stat().st_size==record['digest']['size'] and
          hashlib.sha256(path.read_bytes()).hexdigest()==record['digest']['sha256'],'Provider dependent artifact changed')
    return path


def same_provider_record(left,right):
    return Path(left['path']).resolve()==Path(right['path']).resolve() and all(left['digest'][k]==right['digest'][k] for k in ('size','sha256'))


def provider_objects(manifest):
    spec=importlib.util.spec_from_file_location('source_provider_objects',Path(__file__).with_name('provider-native-artifacts.py'))
    artifact=importlib.util.module_from_spec(spec);spec.loader.exec_module(artifact)
    return artifact.object_records(manifest)


def native_selection(provider_packs,selected_packs,selected_classes,selected_methods):
    spec=importlib.util.spec_from_file_location('selection_native_source_io',Path(__file__).with_name('runtime-provider-source.py'))
    S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
    model=S.module('selection_native_source_model','provider-selection-sites.py')
    return model.project(provider_packs,selected_packs,selected_classes,selected_methods,S)


def frame_overlay(provider_packs):
    refs=[p['manifest']['frame_overlay'] for p in provider_packs or [] if p['manifest'].get('frame_overlay')]
    if not refs:return None
    check(all(r==refs[0] for r in refs),'Providers require conflicting native frame overlays')
    ref=refs[0];path=checked_provider_record(ref['manifest']);checked_provider_record(ref['verification'])
    overlay=json.loads(path.read_text(encoding='utf-8'));checked_provider_record(overlay['object'])
    return dict(reference=ref,object=overlay['object'],replaced_data_object=overlay['source']['replaced_data_object'])


def constructor_selection(provider_packs,selected_packs,selected_classes,selected_methods):
    selected=[p for i,p in enumerate(provider_packs) if i in selected_packs and p['manifest']['family']=='normal-constructor-invocation-v1']
    check(len(selected)<=1,'Duplicate constructor invocation provider')
    if not selected:return '',set(),set(),None
    pack=selected[0];record=pack['manifest']['constructor_invocation_metadata']
    metadata=json.loads(checked_provider_record(record).read_text(encoding='utf-8'))
    spec=importlib.util.spec_from_file_location('diagnostic_constructor_selection',Path(__file__).with_name('constructor-invocation-source.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    text,methods,classes,ready=module.selected_sites(metadata,selected_classes,selected_methods)
    proof=dict(provider_manifest=pack['reference'],metadata=record,ready_indices=ready,
        pending_methods=sorted(methods),pending_classes=sorted(classes),assembly_sha256=hashlib.sha256(text.encode()).hexdigest())
    return text,methods,classes,proof


def globals_index(batch,summary,runtime,coff,provider_packs=None,plan=None):
    frame_runtime_identity(summary,runtime)
    batch,runtime=Path(batch),Path(runtime);known=pe_exports(runtime);providers={};objects=[]
    spec=importlib.util.spec_from_file_location('diagnostic_batch_artifacts',Path(__file__).with_name('closure-batch-artifacts.py'))
    artifacts=importlib.util.module_from_spec(spec);spec.loader.exec_module(artifacts)
    sparse=artifacts.configure(coff,batch,summary,plan)
    def read(record,module):
        p=coff.artifact(batch,record,module);objects.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        return coff.coff_symbols(p,{'WaitOnAddress','WakeByAddressAll'} if module=='string-literals' else frozenset())[0]
    for key,path in [('string_literals','string-literals'),('runtime_metadata','runtime-metadata')]:
        for unit in summary[key]['units']:known.update(read(unit['object'],path))
    if summary['schema']>=23:
        overlay=frame_overlay(provider_packs)
        if overlay:
            check(same_provider_record(overlay['replaced_data_object'],summary['frames']['units'][0]['object']),'Overlay replaces a different base frame object')
            p=checked_provider_record(overlay['object']);known.update(coff.coff_symbols(p)[0])
            objects.append(dict(path=str(p),sha256=overlay['object']['digest']['sha256']))
        else:known.update(read(summary['frames']['units'][0]['object'],'frames'))
        with zipfile.ZipFile(coff.artifact(batch,summary['frames']['index'],'frames')) as z:frame_natives=[json.loads(l) for l in z.read('natives.jsonl').splitlines()]
        for symbol in read(summary['frames']['units'][1]['object'],'frames'):providers.setdefault(symbol,min(m['method'] for m in frame_natives))
    record=summary['numeric_kernel_object'];p=coff.artifact(batch,record)
    known.update(coff.coff_symbols(p)[0]);objects.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    for key,path in [('system_natives','system-natives'),('class_literals','class-literals'),('string_intern','string-intern'),('properties','properties'),('class_bootstrap','class-bootstrap')]:
        with zipfile.ZipFile(coff.artifact(batch,summary[key]['index'],path)) as z:methods=[json.loads(l) for l in z.read('methods.jsonl').splitlines()]
        representative=min(m['method'] for m in methods)
        for unit in summary[key]['units']:
            for symbol in read(unit['object'],path):providers.setdefault(symbol,representative)
    for schema,key,directory in [(16,'unsafe_bootstrap','unsafe-bootstrap'),(17,'vm_registration','vm-registration'),(18,'runtime_resources','runtime-resources'),(19,'bitcasts','bitcasts'),(20,'unsafe_fields','unsafe-fields'),(21,'unsafe_memory','unsafe-memory'),(22,'class_lookup','class-lookup')]:
        if summary['schema']<schema:continue
        module=summary[key]
        with zipfile.ZipFile(coff.artifact(batch,module['index'],directory)) as z:methods=[json.loads(l) for l in z.read('methods.jsonl').splitlines()]
        representative=min(m['method'] for m in methods)
        for unit in module['units']:
            if key=='class_lookup' and unit['id']==1:continue
            for symbol in read(unit['object'],directory):providers.setdefault(symbol,representative)
    if provider_packs:
        for pack in provider_packs:
            metadata=json.loads(runtime.with_name('runtime.json').read_text(encoding='utf-8-sig'))
            check(all(metadata['sources'].get(p)==h for p,h in pack['manifest']['runtime_kernel_sha256'].items()),'Runtime provider imported kernel/heap ABI differs')
            for record in provider_objects(pack['manifest']):
                p=checked_provider_record(record)
                definitions,_=coff.coff_symbols(p,set(pack['manifest'].get('allowed_foreign_imports',[])))
                check(not definitions&known and not definitions&set(providers),'Provider conflicts with runtime/base definitions')
                known.update(definitions);objects.append(dict(path=str(p),sha256=record['digest']['sha256']))
    identity=dict(runtime_dll=str(runtime.resolve()),runtime_sha256=hashlib.sha256(runtime.read_bytes()).hexdigest(),objects=objects)
    if sparse:identity['sparse_artifact_source']=sparse
    if provider_packs:identity['runtime_provider_packs']=[dict(manifest=p['reference'],verification=p['verification']) for p in provider_packs]
    if summary['schema']>=23 and overlay:identity['native_frame_overlay']=overlay
    return known,providers,identity


def missing_symbols(body,known,providers):
    defined=set(re.findall(r'(?m)^\s*(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)',body))
    symbolic=re.compile(r'boom_m\d+(?:_body)?|boom_class\d+|boom_s\d+_\d+|boom_handlers\d+|boom_batch_call_\d+_\d+_\d+|boom_batch_literal_load_\d+_\d+')
    return sorted(s for s in set(re.findall(r'\bboom_\w+\b',body))-defined-known-set(providers)
                  if not symbolic.fullmatch(s) and s not in {'boom_batch_virtual_invoke','boom_batch_array_clone_pool'})


def check(value,message):
    if not value:raise ValueError(message)


def rows(frontiers):
    result=[]
    for i,f in enumerate(sorted(frontiers,key=lambda f:f['symbol']),1):
        check(SYMBOL.fullmatch(f['symbol']) is not None,'Unsupported diagnostic frontier')
        m=f.get('method');b=f.get('binding')
        init=f.get('initialization')
        check(m is not None or b is not None or init is not None,'Diagnostic frontier lacks source identity')
        if init is not None:
            check(m is None and b is None and f['kind']=='unselected_initialization' and
                  init['class_id']==f['class_id'] and init['source_sha256']==f['source_sha256'] and init['diagnostic'] is None and
                  f['symbol']=='boom_batch_initialize_'+str(f['class_id']),'Diagnostic initialization source identity differs')
        if m is not None:
            check(re.fullmatch(r'boom_m'+str(m['id'])+r'(?:_body)?',f['symbol']) is not None,'Diagnostic method symbol differs')
            check((f['kind'] in ('unselected_method','abi_dependency'))==m['assembly_emitted'],'Diagnostic method availability differs')
        if b is not None:check(b['label']==f['symbol'],'Diagnostic protocol source label differs')
        result.append(dict(id=i,category=CATEGORIES.get(f['kind'],3),**f))
    return result


def body(records,context_rows=False):
    out=['option casemap:none\n.const\nALIGN 8\nPUBLIC boom_diagnostic_rows\nboom_diagnostic_rows LABEL BYTE\n']
    for r in records:
        m=r.get('method');b=r.get('binding')
        cls=r['class_id'];method=m['id'] if m is not None else (b['caller_method'] if b is not None else 0)
        constant=0 if b is None else b['constant'];opcode=0 if b is None else b['opcode']
        out.append(f"boom_diagnostic_row{r['id']} DWORD {r['id']},{r['category']},{cls},{method},{constant},{opcode}\n"
              f" QWORD OFFSET boom_diagnostic_label{r['id']},OFFSET boom_diagnostic_source{r['id']},"
              +(f"OFFSET boom_diagnostic_code{r['id']}" if m is not None and m['code_sha256'] else '0')+'\n')
    if not records:out.append(' BYTE 48 DUP(0)\n')
    for r in records:
        texts={'label':r['symbol'],'source':r['source_sha256']}
        if r.get('method') and r['method']['code_sha256']:texts['code']=r['method']['code_sha256']
        for name,text in texts.items():
            out.append(f"boom_diagnostic_{name}{r['id']} LABEL BYTE\n")
            value=text.encode('utf-8')+b'\0'
            for start in range(0,len(value),16):out.append(' BYTE '+','.join(str(b) for b in value[start:start+16])+'\n')
    out.append(f'.data\nALIGN 8\nPUBLIC boom_diagnostic_pool\nboom_diagnostic_pool DWORD 044535450h,1,0,{len(records)}\n'
          ' QWORD OFFSET boom_diagnostic_rows\n DWORD 48,32\n DWORD 0,0,0,0,0,0,0,0\n QWORD 0,0,0,0\n')
    out.append(HELPER.read_text(encoding='utf-8')+'\n.code\n')
    target='boom_diagnostic_stop'
    if context_rows:
        out.extend(path.read_text(encoding='utf-8')+'\n' for path in CONTEXT_HELPERS)
        target='boom_diagnostic_stop_context'
    for r in records:
        out.append(f"PUBLIC {r['symbol']}\n{r['symbol']} PROC\n lea rdx,boom_diagnostic_row{r['id']}\n"
              f" lea r8,boom_diagnostic_pool\n jmp {target}\n{r['symbol']} ENDP\n")
    out.append('END\n');return ''.join(out)


def publish(output,frontiers,admitted,global_identity=None,context_rows=False):
    output=Path(output);records=rows(frontiers)
    asm=body(records,context_rows);(output/'diagnostic-stops.asm').write_text(asm,encoding='utf-8')
    result=dict(schema=1,diagnostic_only=True,stop_kind=STOP_KIND,pool_bytes=96,row_bytes=48,context_bytes=32,
        native_implementations_added=0,provided_methods_added=0,lazy_dispatch=True,dispatch_rows_pruned=False,
        admitted_methods=sorted(admitted),rows=records,global_provider_identity=global_identity,helper_sha256=hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        assembly_sha256=hashlib.sha256((output/'diagnostic-stops.asm').read_bytes()).hexdigest(),
        source_closure_complete=False,game_started=False,world_created=False,full_game_ready=False)
    if context_rows:
        result['context_map_sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in CONTEXT_HELPERS}
    (output/'diagnostic.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
