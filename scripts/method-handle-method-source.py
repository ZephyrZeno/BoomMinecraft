"""Original Class/MethodType source projection for ordinary REF6 MemberName resolution.

The library emits immutable metadata and MASM source. It does not assemble, link,
register a provider, execute Java, or turn metadata resolution into a callable
MethodHandle. Original source selection and explicit full verification remain
separate inputs. No class state, VM readiness, or injected Java field is created.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

FRAGMENT_PATHS={
 'owner':'native/kernels/mhn_resolved_method_owner64.asm.inc',
 'lookup':'native/providers/mhn_static_method_lookup.asm.inc',
 'service':'native/providers/mhn_static_method_resolve.asm.inc'}
HANDLER_ROUTES={'boom_mhn_resolve_external':'boom_mhn_mixed_resolve_external',
                'boom_mhn_member_vm_info_external':'boom_mhn_mixed_vm_info_external'}
NATIVE_ROUTES={'resolve':'(Ljava/lang/invoke/MemberName;Ljava/lang/Class;IZ)Ljava/lang/invoke/MemberName;',
               'getMemberVMInfo':'(Ljava/lang/invoke/MemberName;)Ljava/lang/Object;'}

def check(value,message):
    if not value:raise ValueError(message)

def installed_root():
    for path in Path(__file__).resolve().parents:
        if (path/'scripts/constructor-provider-source.py').is_file() and (path/'native/runtime/java_classes.asm').is_file():return path
    raise ValueError('Installed project source/tool root not found')

def module(name,root=None):
    path=(Path(root).resolve() if root is not None else installed_root())/'scripts'/(name+'.py')
    spec=importlib.util.spec_from_file_location('mhn_method_'+name.replace('-','_'),path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))

def _read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def _route_declarations(classes,frame):
    [owner]=[c for c in classes if (c['origin']['loader'],c['name'])==('bootstrap','java/lang/invoke/MethodHandleNatives')]
    rows=[]
    for name,descriptor in NATIVE_ROUTES.items():
        [row]=[r for r in frame['source']['original_native_declarations'] if r['class_id']==owner['id'] and (r['name'],r['descriptor'])==(name,descriptor)]
        check(row['class_sha256']==owner['origin']['sha256'] and row['flags']==32 and row['access']&0x100 and not row['access']&0x400,'Original normal native Frame/declaration differs')
        rows.append(row)
    return rows

def _class_attributes(raw,C,CP):
    cp=CP.parse_class_pool(raw);r=C.RAW.Reader(raw[10+len(cp['raw']):]);entries=cp['entries']
    def attrs():
        result={}
        for _ in range(r.number(2)):
            entry=entries[r.number(2)];check(entry[0]==1,'Class attribute name is not UTF8');name=entry[2]
            check(name not in result,'Duplicate original Class attribute');result[name]=r.take(r.number(4))
        return result
    r.take(6);r.take(2*r.number(2))
    for _ in range(2):
        for _ in range(r.number(2)):r.take(6);attrs()
    result=attrs();r.end()
    def class_name(payload):
        q=C.RAW.Reader(payload);value=entries[q.number(2)];q.end();check(value[0]==7,'Nest attribute Class constant missing');value=entries[value[2]];check(value[0]==1,'Nest Class UTF8 missing');return value[2]
    host=class_name(result['NestHost']) if 'NestHost' in result else None
    members=[]
    if 'NestMembers' in result:
        q=C.RAW.Reader(result['NestMembers']);count=q.number(2)
        for _ in range(count):members.append(class_name(q.take(2)))
        q.end()
    return host,members
def _normal_layouts(layout_rows,needed,classes):
    result={}
    for row in layout_rows:
        if row['class_id'] not in needed:continue
        check(row['class_id'] not in result,'Duplicate original packed helper layout')
        check(row['candidate'] is not None and row['diagnostic'] is None and row['source_sha256']==classes[row['class_id']]['origin']['sha256'],'Original normal helper layout missing')
        result[row['class_id']]=row['candidate']
    check(set(result)==set(needed),'Required original helper layout is absent')
    return result

def metadata(summary,classes,selection,frame,layouts,normal_methods,*,source_epoch_sha256,root=None):
    """Project explicit decoded original inputs. No selected Java is executed.

    source_epoch_sha256 is the exact byte digest of the explicit selection file,
    not a hash of a reserialized dictionary. project() checks that binding.
    layouts is an iterable of original packed normal layout rows. The NMTH192
    catalogue is separately supplied and every row is joined back to raw Class.
    """
    check(re.fullmatch('[0-9a-f]{64}',source_epoch_sha256) is not None,'Exact source epoch SHA256 required')
    check(selection['source_input_fingerprint']==summary['input_fingerprint'] and selection['source_frame_abi']==summary['frames']['abi']==frame['pool_abi']==3 and frame['method_row_bytes']==32,'Original selected source/Frame ABI differs')
    for key in ('size','sha256'):check(frame['source']['base_frame_index']['digest'][key]==summary['frames']['index']['digest'][key],'Original Frame source identity differs')
    C=module('constructor-provider-source',root);M=module('normal-methods-source',root);F=module('verify-batch-frames',root)
    CP=module('normal-constant-pool-source',root);H=module('verify-batch-metadata',root);I=module('verify-translation-ir',root)
    classes=list(classes)
    check([c['id'] for c in classes]==list(range(len(classes))),'Original Class IDs must be dense')
    loader_keys=summary['class_literals']['loader_keys']
    check(len(loader_keys)==3 and loader_keys[0]=='bootstrap' and len(set(loader_keys))==3,'Actual three-loader JCLS namespace required by this service ABI')
    loader_ids={name:i for i,name in enumerate(loader_keys)}
    lookup,ancestry,parents,omitted=H.source_model(classes);types,runtime,available,resolve=C.inputs(summary,classes)
    original=normal_methods;records=original['records'];ranges=original['ranges'];cap=summary['runtime_metadata']['type_capacity']
    check(len(ranges)==cap and original['row_bytes']==144 and original['range_bytes']==16,'Original normal-method row contract differs')
    frame_flags={r[0]:r[1] for r in frame['source']['rows']}
    method_cap=max((mid for c in classes for mid in c['method_ids']),default=-1)+1
    method_facts=[0]*method_cap;class_methods=[];class_records=[];ifaces=[];packages={};nests=[];all_classes_hash=hashlib.sha256();all_methods_hash=hashlib.sha256()
    magic_accessor=lookup('bootstrap','jdk/internal/reflect/MagicAccessorImpl')
    selected_classes={c['class_id']:c for c in selection['selected_classes']}
    wanted_names=('java/lang/invoke/MemberName','java/lang/invoke/MethodType','java/lang/invoke/ResolvedMethodName','java/lang/Class','java/lang/String','java/lang/Object','java/lang/Throwable','java/lang/Long','java/lang/InternalError','java/lang/IllegalArgumentException','java/lang/NoSuchMethodError','java/lang/IllegalAccessError','java/lang/IncompatibleClassChangeError')
    owners={c['name']:c for c in classes if c['origin']['loader']=='bootstrap' and c['name'] in wanted_names};check(set(owners)==set(wanted_names),'Original method helper Class missing')
    callbacks={};rawsource=C.RawClasses(summary);next_record=0
    try:
        for cls in classes:
            ident=cls['id'];ids=cls['method_ids'];first=ids[0] if ids else 0
            check(ids==list(range(first,first+len(ids))),'Class-local MethodID interval is not contiguous')
            class_methods.append([first,len(ids)])
            loader=cls['origin']['loader'];loadid=loader_ids.get(loader,-1)
            pkg=cls['name'].rpartition('/')[0];pkgid=packages.setdefault((loadid,pkg),len(packages));parent=lookup(loader,cls['superclass']) if cls.get('superclass') else None
            row=dict(parent=0xffffffff if parent is None else parent,access=cls['access'],loader=loadid,package=pkgid,nest_host=ident,nest_status=0,interface_first=0,interface_count=0,package_name=pkg,status=int(ident in available and ident in ancestry and loadid>=0 and not cls.get('parse_error') and not cls['access']&0x8000),magic_accessor=int(magic_accessor is not None and magic_accessor in ancestry.get(ident,set())))
            class_records.append(row)
            if cls.get('parse_error'):
                nests.append((None,[]));continue
            data=rawsource.read(cls);name,access,methods=M.original_methods(data)
            frame_owner,frame_methods=F.original_methods(data)
            check((name,access,len(methods))==(cls['name'],cls['access'],len(ids)),'Original Method inventory differs')
            check(frame_owner==name and len(frame_methods)==len(methods),'Original annotation method inventory differs')
            if cls['name'] in owners and owners[cls['name']]['id']==ident:
                ir=I.Source(data)
                for mid,decl in zip(ids,ir.methods):
                    code=ir.code(decl)
                    wanted_callback=(cls['name'] in ('java/lang/InternalError','java/lang/IllegalArgumentException','java/lang/NoSuchMethodError','java/lang/IllegalAccessError','java/lang/IncompatibleClassChangeError') and (decl['name'],decl['descriptor'])==('<init>','(Ljava/lang/String;)V'))
                    if wanted_callback:
                        key=cls['name']+'#'+decl['name']+decl['descriptor'];code_sha=hashlib.sha256(code['bytes']).hexdigest() if code else None
                        selected=selection['selected_methods'].get(str(mid));check(code_sha and selected==dict(class_id=ident,name=decl['name'],descriptor=decl['descriptor'],source_sha256=cls['origin']['sha256'],code_sha256=code_sha),'Required original callback is not selected: '+key)
                        callbacks[key]=dict(method=mid,class_id=ident,name=decl['name'],descriptor=decl['descriptor'],source_sha256=cls['origin']['sha256'],code_sha256=code_sha,symbol='boom_m'+str(mid))
            host,members=_class_attributes(data,C,CP);nests.append((host,members))
            expected=[]
            for mid,decl,frame_decl in zip(ids,methods,frame_methods):
                check(all(frame_decl[k]==decl[k] for k in ('name','descriptor','access')),'Original frame annotation declaration differs')
                trusted=cls['origin']['source_id'].startswith('jdk:') and not cls['origin'].get('generated')
                caller_sensitive=int(trusted and 'Ljdk/internal/reflect/CallerSensitive;' in frame_decl['annotations'])
                if mid in frame_flags:check(bool(frame_flags[mid]&8)==bool(caller_sensitive),'Provided original Frame CallerSensitive fact differs: '+str(mid)+' '+cls['name']+'.'+decl['name'])
                # Abstract/unprovided Java declarations remain real lookup rows.
                # Their source annotations do not require an executable Frame.
                method_facts[mid]=caller_sensitive
                if decl['name'] in ('<init>','<clinit>'):continue
                check(next_record<len(records),'Normal method catalogue truncated');record=records[next_record]
                params,returns=M.descriptor_types(decl['descriptor'])
                check(all(record[k]==v for k,v in dict(owner=ident,method=mid,slot=decl['slot'],name=decl['name'],descriptor=decl['descriptor'],source_sha256=cls['origin']['sha256'],modifiers=decl['access']&0x1dff,parameters=[resolve(loader,p) for p in params],return_type=resolve(loader,returns)).items()),'Actual normal method row differs from original Class source: '+cls['name'])
                expected.append(record);all_methods_hash.update(json.dumps([mid,ident,decl['slot'],decl['name'],decl['descriptor'],decl['access'],method_facts[mid],cls['origin']['sha256']],separators=(',',':')).encode()+b'\n');next_record+=1
            rr=ranges[ident];check(rr['first']==next_record-len(expected) and rr['count']==len(expected),'Normal-method per-Class range differs')
            all_classes_hash.update(json.dumps([ident,cls['origin']['sha256'],ids],separators=(',',':')).encode()+b'\n')
    finally:rawsource.close()
    check(next_record==len(records),'Unexpected trailing normal method rows')
    for cls in classes:
        ident=cls['id'];hostname,members=nests[ident];row=class_records[ident]
        if hostname is not None:
            host=lookup(cls['origin']['loader'],hostname)
            valid=host is not None and class_records[host]['package']==row['package'] and nests[host][0] is None and cls['name'] in nests[host][1]
            row['nest_host']=host if valid else 0xffffffff;row['nest_status']=1 if valid else 2
        else:row['nest_status']=1
        if not row['status']:
            row['interface_first']=len(ifaces);continue
        seen=set();active=set();order=[]
        def visit(i):
            check(i not in active,'Original interface hierarchy cycle')
            if i in seen:return
            seen.add(i);active.add(i)
            c=classes[i]
            for n in c['interfaces']:
                j=lookup(c['origin']['loader'],n)
                if j is None:row['status']=0;continue
                order.append(j);visit(j)
            p=class_records[i]['parent']
            if p!=0xffffffff and not c['access']&0x200:visit(p)
            active.remove(i)
        visit(ident);row['interface_first']=len(ifaces);seen_ifaces=set()
        for j in order:
            if j not in seen_ifaces:ifaces.append(j);seen_ifaces.add(j)
        row['interface_count']=len(ifaces)-row['interface_first']
    names={(t['defining_loader'],t['name']):t['id'] for t in types};type_rows={t['id']:t for t in types};type_resolutions=[]
    for loader in loader_keys:
        values=[]
        for tid in range(cap):
            t=type_rows.get(tid)
            desc=None if t is None else ('L'+t['name']+';' if t['kind'] in (1,2) else t['name'])
            value=resolve(loader,desc) if desc is not None else None;values.append(value if value is not None else 0xffffffff)
        type_resolutions.append(values)
    needed={o['id'] for o in owners.values()}
    layouts=_normal_layouts(layouts,needed,classes)
    offsets={}
    for name in ('java/lang/invoke/MemberName','java/lang/invoke/MethodType','java/lang/Class','java/lang/String'):
        cls=owners[name];fields=layouts[cls['id']]['fields'];offsets[name]={f['member']['name']:f['offset'] for f in fields if f['member']['owner']==cls['id']}
    rmn=owners['java/lang/invoke/ResolvedMethodName'];chosen=selected_classes.get(rmn['id']);check(chosen and chosen['source_sha256']==rmn['origin']['sha256'] and chosen['diagnostic'] is None,'New genuine RMN source admission is required')
    check(layouts[rmn['id']]['payload_bytes']==0 and layouts[rmn['id']]['reference_prefix']==0 and rmn['fields']==[],'RMN must remain the actual zero-field original Java Class')
    row=dict(schema=1,scope='Prepared original-source method catalogue; no Java/native execution or synthetic Java fields',source_manifest=None,source_full_verification=None,source_admission_verified=False,source_epoch_token=int(source_epoch_sha256[:16],16) or 1,original_class_count=len(classes),original_method_capacity=method_cap,type_descriptor_prefix_capacity=cap,normal_method_rows=len(records),original_Class_inventory_sha256=all_classes_hash.hexdigest(),original_method_inventory_sha256=all_methods_hash.hexdigest(),owners={n:dict(class_id=c['id'],source_sha256=c['origin']['sha256']) for n,c in owners.items()},callbacks=callbacks,offsets=offsets,layouts={n:layouts[c['id']] for n,c in owners.items()},Class_array_type=names['bootstrap','[Ljava/lang/Class;'],Object_array_type=names['bootstrap','[Ljava/lang/Object;'],class_records=class_records,class_method_ranges=class_methods,interface_holders=ifaces,method_facts=method_facts,namespace_type_resolutions=type_resolutions,additional_oop_roots=[dict(symbol='boom_mhn_resolved_method_roots',count=8192,kind='strong_oop')],original_Java_Code_changed=False,RMN_VM_allocation_calls_original_constructor=False,metadata_only_RMN_does_not_claim_callable_MethodHandle=True)
    row['loader_keys']=loader_keys
    row['registration_routes']=_route_declarations(classes,frame)
    for name in ('java/lang/invoke/ResolvedMethodName','java/lang/Long'):
        cls=owners[name];selected=selected_classes.get(cls['id'])
        check(selected and selected['source_sha256']==cls['origin']['sha256'] and selected['diagnostic'] is None,'Original boxing/RMN Class must be selected normally: '+name)
    for callback in callbacks.values():check(selection['selected_function_sha256'].get(callback['symbol']+'_body'),'Required error callback must have its original emitted body')
    return row

def words(label,text):
    raw=text.encode('utf-16-le','surrogatepass');values=[int.from_bytes(raw[i:i+2],'little') for i in range(0,len(raw),2)]
    return label+' LABEL WORD\n'+''.join(' WORD '+','.join(map(str,values[i:i+16]))+'\n' for i in range(0,len(values),16))
def imports(procs,data):return ''.join('EXTERN '+s+':PROC\n' for s in sorted(procs))+''.join('EXTERN '+s+':BYTE\n' for s in sorted(data))
def owner_assembly(*,root=None,fragments=None):
    fragments=_fragments(root,fragments)
    return 'option casemap:none\n'+imports({'AcquireSRWLockExclusive','ReleaseSRWLockExclusive'},{'boom_mhn_method_owner_pool'})+fragments['owner'].read_text(encoding='utf-8')+'\nEND\n'
def method_assembly(m,*,root=None,fragments=None):
    fragments=_fragments(root,fragments)
    classes=m['owners'];cid=lambda n:classes[n]['class_id'];callbacks=m['callbacks'];off=m['offsets']
    proc={'boom_heap_contains','boom_object_check','boom_runtime_row','boom_java_class_typeid','boom_java_class_load','boom_class_ensure32','boom_object_new','boom_exception_set32','boom_java_property_copy','boom_typed_multi_new','boom_mhn_method_owner_enter','boom_mhn_method_owner_leave','boom_mhn_method_owner_intern','boom_mhn_method_owner_find','boom_mhn_method_scratch_acquire','boom_mhn_method_scratch_set','boom_mhn_method_scratch_release','boom_mhn_resolve_external','boom_mhn_member_vm_info_external'}
    proc|={r['symbol'] for k,r in callbacks.items() if not k.startswith('java/lang/Long#')}
    data={'boom_heap_ptr','boom_runtime_type_map','boom_java_class_pool','boom_mhn_field_pool','boom_normal_method_pool','boom_java_platform_properties_pool','boom_mhn_method_owner','boom_mhn_method_records','boom_mhn_resolved_method_roots',f"boom_t{m['Class_array_type']}",f"boom_t{m['Object_array_type']}"}
    for n in ('java/lang/invoke/MethodType','java/lang/invoke/MemberName','java/lang/String','java/lang/invoke/ResolvedMethodName'):data|={f'boom_layout{cid(n)}',f'boom_t{cid(n)}'}
    data|={f"boom_t{cid('java/lang/Throwable')}",f"boom_class{cid('java/lang/invoke/ResolvedMethodName')}",f"boom_class{cid('java/lang/Long')}",f"boom_layout{cid('java/lang/Long')}"}
    [longvalue]=[f for f in m['layouts']['java/lang/Long']['fields'] if f['member']['owner']==cid('java/lang/Long') and (f['member']['name'],f['member']['descriptor'],f['member']['access'])==('value','J',0x12)]
    if longvalue['storage_bytes']!=8 or longvalue['reference']:raise ValueError('Original Long.value layout differs')
    errors=('java/lang/InternalError','java/lang/IllegalArgumentException','java/lang/NoSuchMethodError','java/lang/IllegalAccessError','java/lang/IncompatibleClassChangeError')
    for n in errors:data|={f'boom_class{cid(n)}',f'boom_layout{cid(n)}'}
    text=['option casemap:none\n',imports(proc,data),'.const\nALIGN 8\nPUBLIC boom_mhn_method_owner_pool\n']
    text+=['boom_mhn_method_owner_pool DWORD 04D485250h,1,128,4096\n',
        ' QWORD OFFSET boom_heap_ptr,OFFSET boom_mhn_method_records,OFFSET boom_mhn_resolved_method_roots\n DWORD 128,8192\n',
        f" QWORD 0{m['source_epoch_token']:016X}h,0\n QWORD OFFSET boom_class{cid('java/lang/invoke/ResolvedMethodName')},OFFSET boom_layout{cid('java/lang/invoke/ResolvedMethodName')},OFFSET boom_java_class_pool,OFFSET boom_runtime_type_map\n QWORD OFFSET mhmm_class_method_ranges\n",
        f" DWORD {m['original_method_capacity']},{cid('java/lang/invoke/ResolvedMethodName')},{m['original_class_count']},0\n QWORD OFFSET boom_normal_method_pool\nALIGN 8\nPUBLIC boom_mhn_method_pool\n",
        f"boom_mhn_method_pool DWORD 04D48524Dh,1,512,{m['type_descriptor_prefix_capacity']}\n",
        ' QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_java_class_pool,OFFSET boom_mhn_field_pool\n',
        ' QWORD OFFSET boom_mhn_method_owner,OFFSET boom_mhn_method_owner_pool,OFFSET boom_normal_method_pool,OFFSET mhmm_classes\n',
        ' QWORD OFFSET mhmm_interface_holders,OFFSET mhmm_class_method_ranges,OFFSET mhmm_method_facts\n',
        f" QWORD OFFSET boom_layout{cid('java/lang/invoke/MethodType')},OFFSET boom_t{cid('java/lang/invoke/MethodType')},OFFSET boom_layout{cid('java/lang/invoke/MemberName')},OFFSET boom_t{cid('java/lang/invoke/MemberName')},OFFSET boom_layout{cid('java/lang/String')},OFFSET boom_t{cid('java/lang/String')},OFFSET boom_t{m['Class_array_type']}\n",
        f" QWORD OFFSET boom_class{cid('java/lang/invoke/ResolvedMethodName')},OFFSET boom_layout{cid('java/lang/invoke/ResolvedMethodName')},OFFSET boom_t{cid('java/lang/Throwable')},OFFSET boom_java_platform_properties_pool,OFFSET mhmm_exceptions,OFFSET mhmm_messages\n",
        f" DWORD {m['original_class_count']},{m['original_method_capacity']}\n QWORD OFFSET mhmm_namespace_types\n"]
    offsets=[off['java/lang/invoke/MemberName'][n] for n in ('clazz','name','type','method','resolution','flags')]
    offsets += [off['java/lang/invoke/MethodType']['rtype'],off['java/lang/invoke/MethodType']['ptypes'],off['java/lang/Class']['classLoader'],off['java/lang/Class']['module'],off['java/lang/String']['value'],off['java/lang/String']['coder'],len(m['interface_holders']),0,cid('java/lang/Object'),cid('java/lang/invoke/ResolvedMethodName')]
    text+=[' DWORD '+','.join(map(str,offsets))+'\n',f" QWORD OFFSET boom_class{cid('java/lang/Long')},OFFSET boom_t{m['Object_array_type']}\n",f" DWORD {cid('java/lang/invoke/MethodType')},{cid('java/lang/invoke/MemberName')},{cid('java/lang/String')},264,{m['Class_array_type']},{longvalue['offset']}\n QWORD OFFSET boom_layout{cid('java/lang/Long')}\n QWORD 22 DUP(0)\nALIGN 8\nmhmm_exceptions LABEL QWORD\n"]
    for n in errors:text.append(f" QWORD OFFSET boom_class{cid(n)},OFFSET boom_layout{cid(n)},OFFSET {callbacks[n+'#<init>(Ljava/lang/String;)V']['symbol']}\n")
    messages=('mname is null','obsolete MemberName format','nothing to resolve','method resolution failed','method access denied','Expected static method')
    text.append('ALIGN 8\nmhmm_messages LABEL BYTE\n')
    for i,s in enumerate(messages):text.append(f' QWORD OFFSET mhmm_message{i}\n DWORD {len(s.encode("utf-16-le"))//2},0\n')
    for i,s in enumerate(messages):text.append(words('mhmm_message'+str(i),s))
    text.append('ALIGN 8\nmhmm_classes LABEL BYTE\n')
    for r in m['class_records']:
        text.append(' DWORD '+','.join(str(r[k]) for k in ('parent','access','loader','package','nest_host','nest_status','interface_first','interface_count'))+'\n QWORD 0\n')
        text.append(f" DWORD {len(r['package_name'].encode('utf-16-le'))//2},{r['status']},0,{r['magic_accessor']}\n QWORD 0\n")
    text.append('ALIGN 4\nmhmm_interface_holders LABEL DWORD\n')
    for at in range(0,len(m['interface_holders']),16):text.append(' DWORD '+','.join(map(str,m['interface_holders'][at:at+16]))+'\n')
    text.append('ALIGN 8\nmhmm_class_method_ranges LABEL DWORD\n')
    text.extend(' DWORD '+','.join(map(str,r))+'\n' for r in m['class_method_ranges'])
    text.append('ALIGN 4\nmhmm_method_facts LABEL BYTE\n')
    for at in range(0,len(m['method_facts']),32):text.append(' BYTE '+','.join(map(str,m['method_facts'][at:at+32]))+'\n')
    text.append('ALIGN 4\nmhmm_namespace_types LABEL DWORD\n')
    for values in m['namespace_type_resolutions']:
        for at in range(0,len(values),16):text.append(' DWORD '+','.join(map(str,values[at:at+16]))+'\n')
    text.extend([fragments['lookup'].read_text(encoding='utf-8'),fragments['service'].read_text(encoding='utf-8'),'\nEND\n'])
    return ''.join(text)

def _fragments(root=None,fragments=None):
    if fragments is None:
        base=Path(root).resolve() if root is not None else installed_root()
        fragments={k:base/v for k,v in FRAGMENT_PATHS.items()}
    check(set(fragments)==set(FRAGMENT_PATHS),'Explicit owner/lookup/service fragments required')
    return {k:Path(v) for k,v in fragments.items()}

def routing_assembly(metadata,registration,*,root=None):
    """Rebuild the original binding table, then replace exactly two callbacks.

    The normal field source API owns the original table/kernel. Every other
    native declaration, Frame identity, field handler and publication rule is
    left in that original source. No second native adapter is manufactured.
    """
    if 'registration' in registration:registration=registration['registration']
    for decl in metadata['registration_routes']:
        [row]=[r for r in registration['rows'] if r['method']==decl['id']]
        check(all(row[k]==decl[v] for k,v in (('class_id','class_id'),('name','name'),('descriptor','descriptor'),('access','access'),('source_sha256','class_sha256'))),'Original routing table/native declaration differs')
        check(row['frame_flags']==decl['flags'] and row['handler'] in HANDLER_ROUTES and row['support']==1,'Original native callback role differs')
    source=module('method-handle-field-source',root).registration_assembly({'registration':registration})
    for old,new in HANDLER_ROUTES.items():
        pattern=r'\b'+re.escape(old)+r'\b';check(len(re.findall(pattern,source))>=2,'Original handler declaration/data reference missing')
        source=re.sub(pattern,new,source)
    return source

def render(metadata,registration=None,*,root=None,fragments=None):
    result={'mhn-resolved-method-owner':owner_assembly(root=root,fragments=fragments),
            'mhn-static-method-resolver':method_assembly(metadata,root=root,fragments=fragments)}
    if registration is not None:result['mhn-method-field-routing-table']=routing_assembly(metadata,registration,root=root)
    return result

def project(summary_file,classes_file,selection_file,frame_file,layouts_file,normal_methods_file,*,source_verification=None):
    summary,selection,frame=map(_read,(summary_file,selection_file,frame_file))
    check(selection['source_batch_summary_sha256']==artifact(summary_file)['digest']['sha256'] and selection['source_classes_sha256']==artifact(classes_file)['digest']['sha256'],'Explicit source selection/plan/summary differ')
    check(Path(layouts_file).resolve()==Path(summary['layouts']['path']).resolve() and all(artifact(layouts_file)['digest'][k]==summary['layouts']['digest'][k] for k in ('size','sha256')),'Original packed layout source differs')
    proof=_read(source_verification) if source_verification is not None else None
    if proof is not None:check(proof.get('verified') is True and proof['closure_manifest_sha256']==artifact(selection_file)['digest']['sha256'],'Completed original SourceV identity differs')
    with Path(classes_file).open(encoding='utf-8') as stream:classes=[json.loads(line) for line in stream]
    with Path(layouts_file).open(encoding='utf-8') as stream:
        result=metadata(summary,classes,selection,frame,(json.loads(line) for line in stream),_read(normal_methods_file),source_epoch_sha256=artifact(selection_file)['digest']['sha256'])
    result['source_manifest']=artifact(selection_file);result['source_full_verification']=artifact(source_verification) if proof is not None else None;result['source_admission_verified']=proof is not None
    result['inputs']={k:artifact(p) for k,p in dict(summary=summary_file,classes=classes_file,selection=selection_file,frame=frame_file,layouts=layouts_file,normal_methods=normal_methods_file,source_library=__file__).items()}
    return result

def main(args):
    # Reject an invalid output before reading any project input model or mkdir.
    output=args.output.resolve();base=installed_root()
    check(any(output.is_relative_to(base/name) for name in ('.boom','target','dist')),'Output must stay in this installed project .boom, target or dist')
    check(not output.exists(),'Source output must be create-new')
    value=project(args.summary,args.classes,args.selection,args.frames,args.layouts,args.normal_methods,source_verification=args.source_verification)
    registration=_read(args.registration) if args.registration is not None else None
    sources=render(value,registration);output.mkdir(parents=True)
    with (output/'model.json').open('x',encoding='utf-8',newline='\n') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    for role,text in sources.items():
        with (output/(role+'.asm')).open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('summary','classes','selection','frames','layouts','normal-methods','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-verification',type=Path);parser.add_argument('--registration',type=Path)
    main(parser.parse_args())
