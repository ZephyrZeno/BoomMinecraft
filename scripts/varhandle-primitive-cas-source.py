"""Explicit original-Class field-family projection and primitive comparison ASM.

field_directory(summary, classes, selection, diagnostic, layouts, frame, ...)
rebuilds original field families and access modes without an external directory.
index(...) activates only the ABI's Int/Long instance comparison rows. project()
binds explicit input files and an existing full Source proof; render() emits two
ASM units. These APIs do not compile, select Java, register packs or run a VM.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ABI_FILE=ROOT/'native-config/varhandle-primitive-cas-abi.json'
FRAGMENT=ROOT/'native/providers/varhandle_primitive_cas.asm.inc'
FAMILY=re.compile(r'java/lang/invoke/VarHandle([^/$]+)\$Field(Instance|Static)(ReadOnly|ReadWrite)')
MODULES={}


def check(ok,message):
    if not ok:raise ValueError(message)


def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=sha))


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def checked(row):
    expected=row.get('digest',row);actual=artifact(row['path'])
    check(all(actual['digest'][k]==expected[k] for k in ('size','sha256')),'Original input changed: '+row['path'])
    return Path(actual['path'])


def module(name):
    if name not in MODULES:
        spec=importlib.util.spec_from_file_location('primitive_source_'+name.replace('-','_'),ROOT/'scripts'/(name+'.py'))
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);MODULES[name]=value
    return MODULES[name]


def parameters(descriptor):
    check(descriptor.startswith('('),'Method descriptor start')
    pos=1;result=[]
    while descriptor[pos]!=')':
        start=pos
        while descriptor[pos]=='[':pos+=1
        if descriptor[pos]=='L':pos=descriptor.index(';',pos)+1
        else:
            check(descriptor[pos] in 'ZBCSIJFD','Method descriptor primitive');pos+=1
        result.append(descriptor[start:pos])
    return result,descriptor[pos+1:]


def field_directory(summary,all_classes,selection,diagnostic,layouts_input,frame,reference_runtime_class=None):
    """Resolve every original field-family/static-mode declaration from source.

    Directory presence is source metadata only. Missing static targets remain
    explicit, and native catalog presence is not execution/domain acceptance.
    """
    I,R=module('verify-translation-ir'),module('constructor-provider-source')
    source=selection
    check([c['id'] for c in all_classes]==list(range(len(all_classes))),'Original Class plan must be dense')
    names={'java/lang/invoke/VarHandle','java/lang/invoke/VarHandle$AccessMode','java/lang/invoke/VarHandle$AccessType',
           'java/lang/invoke/VarForm','java/lang/invoke/VarHandles','jdk/internal/misc/Unsafe',
           'java/lang/Class','java/util/Objects','java/lang/Object','java/lang/Float','java/lang/Double'}
    classes={row['name']:row for row in all_classes if row['origin']['loader']=='bootstrap' and
             (FAMILY.fullmatch(row['name']) or row['name'] in names)}
    family_names=[name for name in classes if FAMILY.fullmatch(name)]
    check(family_names and len(family_names)==len(set(family_names)),'Original field-family catalogue missing or ambiguous')
    raws,methods,method_keys={}, {}, {}
    reader=R.RawClasses(summary)
    try:
        def add_class(cls):
            blob = reader.read(cls)
            raw = I.Source(blob)
            check(I.digest(blob)['sha256']==cls['origin']['sha256'] and raw.name==cls['name'] and len(raw.methods)==len(cls['method_ids']), 'Original Class identity/declaration ordering')
            raws[cls['name']] = raw
            check([{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==cls['fields'],
                  'Original Class field declaration order differs')
            for ident, method in zip(cls['method_ids'],raw.methods):
                code = raw.code(method)
                expected = dict(class_id=cls['id'],name=method['name'],descriptor=method['descriptor'],
                                code_sha256=I.digest(code['bytes'])['sha256'] if code else None,source_sha256=cls['origin']['sha256'])
                selected = source['selected_methods'].get(str(ident))
                if selected:
                    check(selected==expected, 'Selected original Java record differs from original Class/Code')
                body = source['selected_function_sha256'].get('boom_m'+str(ident)+'_body')
                row = dict(method=ident,class_id=cls['id'],owner=cls['name'],name=method['name'],descriptor=method['descriptor'],
                           access=method['access'],source_sha256=cls['origin']['sha256'],code_sha256=expected['code_sha256'],
                           Code_bytes=len(code['bytes']) if code else 0,selected_original_Code=selected,
                           provided_backend_body=body,normal_symbol='boom_m'+str(ident),
                           normal_entry_source_sha256=source['selected_function_sha256'].get('boom_m'+str(ident)))
                methods[ident] = row
                method_keys[(cls['name'],method['name'],method['descriptor'])] = ident
        for cls in classes.values():
            add_class(cls)
        native_declarations = [row for row in methods.values() if row['owner']=='java/lang/invoke/VarHandle' and row['access']&0x180==0x180]
        mode_names = {row['name'] for row in native_declarations}
        native_by_name = {row['name']:row for row in native_declarations}
        check(len(mode_names)==len(native_declarations), 'No ambiguous original signature-polymorphic declarations')
        original_native={row['id']:row for row in frame['source']['original_native_declarations']}
        for row in native_declarations:
            decl=original_native.get(row['method'])
            check(decl and all(decl[k]==row[v] for k,v in [('class_id','class_id'),('name','name'),('descriptor','descriptor'),('access','access')]) and
                  decl['class_sha256']==row['source_sha256'] and decl['flags']&32 and row['code_sha256'] is None,
                  'Original signature-polymorphic declaration/normal Frame differs')
        # Read actual enum construction operands; no camel-case or ordinal guess.
        raw = raws['java/lang/invoke/VarHandle$AccessMode']
        clinit = next(method for method in raw.methods if method['name']=='<clinit>')
        bytecode = raw.code(clinit)['bytes']
        modes, active = [], None
        for ins in I.stream(bytecode):
            pc, op = ins['pc'], ins['opcode']
            if op==187 and raw.class_name(int.from_bytes(bytecode[pc+1:pc+3],'big'))==raw.name:
                active = dict(strings=[],integers=[],access_types=[])
            elif active is not None:
                if op in (18,19):
                    cp = bytecode[pc+1] if op==18 else int.from_bytes(bytecode[pc+1:pc+3],'big')
                    if raw.cp[cp][0]==8:
                        active['strings'].append(raw.text(raw.cp[cp][1]))
                elif 2<=op<=8:
                    active['integers'].append(op-3)
                elif op in (16,17):
                    active['integers'].append(int.from_bytes(bytecode[pc+1:pc+(2 if op==16 else 3)],'big',signed=True))
                elif op==178:
                    ref = raw.member(int.from_bytes(bytecode[pc+1:pc+3],'big'))
                    if ref['owner']=='java/lang/invoke/VarHandle$AccessType':
                        active['access_types'].append(ref['name'])
                elif op==179:
                    ref = raw.member(int.from_bytes(bytecode[pc+1:pc+3],'big'))
                    if ref['owner']==raw.name:
                        check(active['strings'][0]==ref['name'] and len(active['strings'])==2 and len(active['integers'])==1 and len(active['access_types'])==1,
                              'Original AccessMode enum constructor shape differs')
                        operation = active['strings'][1]
                        check(operation in native_by_name, 'Enum access mode lacks original native declaration')
                        modes.append(dict(name=operation,enum_name=ref['name'],ordinal=active['integers'][0],access_type=active['access_types'][0],
                                          native_declaration=native_by_name[operation],baseline_reference_CAS_bridge_operation=1 if operation=='compareAndSet' else None))
                        active = None
        check({row['name'] for row in modes}==mode_names and [row['ordinal'] for row in modes]==list(range(len(modes))), 'All actual signature-polymorphic modes must be accounted for')
        def calls(ident):
            row = methods[ident]
            raw = raws[row['owner']]
            method = raw.methods[classes[row['owner']]['method_ids'].index(ident)]
            code = raw.code(method)
            result = []
            if code is None:
                return result
            for ins in I.stream(code['bytes']):
                op = ins['opcode']
                if 182<=op<=185:
                    cp = int.from_bytes(code['bytes'][ins['pc']+1:ins['pc']+3],'big')
                    member = raw.member(cp)
                    result.append(dict(pc=ins['pc'],opcode=op,constant=cp,**member))
            return result
        def resolve_decl(owner,name,descriptor):
            seen = set()
            while owner in raws and owner not in seen:
                seen.add(owner)
                ident = method_keys.get((owner,name,descriptor))
                if ident is not None:
                    return ident
                owner = raws[owner].parent
            return None
        def unsafe_dependencies(ident):
            pending, seen, edges, terminals, gaps, other_helpers = [ident],set(),[],{},[],[]
            while pending:
                current = pending.pop()
                if current in seen:
                    continue
                seen.add(current)
                row = methods[current]
                if row['access']&0x100:
                    terminal = dict(row)
                    terminal['selected_Unsafe_memory_catalog_entry'] = source.get('selected_Unsafe_memory_natives',{}).get(str(current))
                    terminal['runtime_domain_or_execution_acceptance_claimed'] = False
                    terminals[current] = terminal
                    continue
                if row['owner']=='jdk/internal/misc/Unsafe' and (not row['selected_original_Code'] or not row['provided_backend_body']):
                    gaps.append(dict(method=current,reason='Unsafe Java wrapper Code not selected or backend body not provided'))
                for ref in calls(current):
                    if ref['owner']!='jdk/internal/misc/Unsafe':
                        if row['owner']=='jdk/internal/misc/Unsafe':
                            target = resolve_decl(ref['owner'],ref['name'],ref['descriptor'])
                            other_helpers.append(dict(caller=current,callee=methods.get(target),**ref))
                        continue
                    target = resolve_decl(ref['owner'],ref['name'],ref['descriptor'])
                    edges.append(dict(caller=current,callee=target,**ref))
                    if target is None:
                        gaps.append(dict(reason='No matching original Unsafe declaration',**ref))
                    else:
                        pending.append(target)
            return dict(original_Unsafe_methods=[methods[mid] for mid in sorted(seen) if methods[mid]['owner']=='jdk/internal/misc/Unsafe'],
                        original_Unsafe_call_edges=edges,other_calls_from_Unsafe_wrappers=other_helpers,
                        native_terminals=[terminals[mid] for mid in sorted(terminals)],source_gaps=gaps,
                        transitive_scope='Only original Unsafe-to-Unsafe Java calls are expanded; other helper calls remain explicit direct dependencies')
        layouts={row['class_id']:row for row in layouts_input if row['class_id'] in {classes[name]['id'] for name in family_names}}
        check(len(layouts)==len(family_names),'Every original field family needs its actual source layout')
        # Join normal receiver layouts to actual UFMP/FMAPPROC identities.
        # Symbols are source bindings only, not machine addresses or new ASM.
        owner_ids = {f['member']['owner'] for layout in layouts.values() if layout.get('candidate') for f in layout['candidate']['fields']}
        ufmp_by_slot = {}
        with zipfile.ZipFile(checked(summary['unsafe_fields']['index'])) as archive:
            with archive.open('fields.jsonl') as stream:
                for line in stream:
                    row = json.loads(line)
                    if row['class_id'] in owner_ids:
                        ufmp_by_slot[(row['class_id'],row['field_index'])] = row
        wanted_maps = {row['address_map'] for row in ufmp_by_slot.values()}
        actual_maps = {}
        with zipfile.ZipFile(checked(summary['runtime_metadata']['index'])) as archive:
            with archive.open('fields.jsonl') as stream:
                for line in stream:
                    row = json.loads(line)
                    if row['id'] in wanted_maps:
                        actual_maps[row['id']] = row
        family_fields = {}
        for ident,layout in layouts.items():
            bindings = []
            check(layout.get('candidate') is not None,'Current original field family layout must be provided')
            for f in layout['candidate']['fields']:
                m = f['member']
                u = ufmp_by_slot[(m['owner'],m['index'])]
                owner=next(c for c in classes.values() if c['id']==m['owner'])
                decl=raws[owner['name']].fields[m['index']]
                check(all(decl[k]==m[k] for k in ('name','descriptor','access')) and u['class_sha256']==owner['origin']['sha256'],
                      'Actual original field/declared slot/Class hash differs')
                check(all(m[key]==u[key] for key in ('name','descriptor','access')),'Original field/layout/UFMP text identity differs')
                fm = actual_maps[u['address_map']]
                [physical] = [row for row in fm['rows'] if row['receiver_class']==ident]
                check(physical['offset']==f['offset'] and u['storage_bytes']==f['storage_bytes'] and fm['storage_bytes']==f['storage_bytes'],
                      'Actual family receiver field address differs from source layout')
                bindings.append(dict(name=m['name'],descriptor=m['descriptor'],declaring_class=m['owner'],declared_slot=m['index'],
                                     UFMP_id=u['id'],UFMP_kind=u['kind'],physical_offset=f['offset'],storage_bytes=f['storage_bytes'],
                                     reference=f['reference'],FMAPPROC_symbol='boom_field_map'+str(fm['id']),
                                     exact_receiver_class=ident,exact_source_receiver_row=physical))
            family_fields[ident] = bindings
        families, dispatch = [], []
        target_cache = {}
        for name in sorted(family_names,key=lambda name:classes[name]['id']):
            cls = classes[name]
            match = FAMILY.fullmatch(name)
            initializer = next((methods[mid] for mid in cls['method_ids'] if methods[mid]['name']=='<clinit>'),None)
            family = dict(runtime_class=cls['id'],runtime_class_name=name,value_family=match[1],storage=match[2],mutability=match[3],
                          direct_superclass=cls['superclass'],source_sha256=cls['origin']['sha256'],runtime_layout=layouts.get(cls['id']),instance_field_bindings=family_fields[cls['id']],initializer=initializer)
            families.append(family)
            for mode in modes:
                owner = name
                targets = []
                while owner in raws:
                    targets = [methods[mid] for mid in classes[owner]['method_ids'] if methods[mid]['name']==mode['name'] and methods[mid]['access']&8]
                    if targets:
                        break
                    owner = raws[owner].parent
                check(len(targets)<=1, 'Do not guess between overloaded static access-mode implementations')
                row = dict(operation=mode['name'],source_AccessMode_ordinal=mode['ordinal'],source_AccessMode_enum=mode['enum_name'],
                           access_type=mode['access_type'],runtime_class=cls['id'],runtime_class_name=name,value_family=match[1],storage=match[2],mutability=match[3],
                           baseline_bridge_operation=mode['baseline_reference_CAS_bridge_operation'],activated_by_this_directory=False,
                           within_existing_reference_CAS_source_contract=(cls['id']==reference_runtime_class and mode['name']=='compareAndSet'),
                           field_layout_bindings={label:next((f for f in family_fields[cls['id']] if f['name']==field_name),None) for label,field_name in [('field_offset','fieldOffset'),('receiver_type','receiverType'),('field_type','fieldType'),('static_base','base')]},
                           target=None,gaps=[])
                if not targets:
                    row['status'] = 'no_original_static_target_for_this_family_mode'
                    row['gaps'].append('ReadOnly or value-family mode unsupported by original implementation; never inherit the nonstatic VarHandle native declaration as a Java target')
                else:
                    target = targets[0]
                    row.update(target=target,declaring_class=target['class_id'],declaring_class_name=target['owner'],inherited=target['owner']!=name)
                    args_, result = parameters(target['descriptor'])
                    check(args_ and args_[0]=='Ljava/lang/invoke/VarHandle;', 'Original static access target must take VarHandle first')
                    row['target_shape'] = dict(parameters=args_,result=result,explicit_arguments_after_handle=len(args_)-1,
                                               field_coordinate_count=1 if match[2]=='Instance' else 0,
                                               signature_polymorphic_adaptation_not_implemented_by_directory=True)
                    if target['method'] not in target_cache:
                        refs = calls(target['method'])
                        target_cache[target['method']] = dict(direct_original_calls=refs,Unsafe_dependencies=unsafe_dependencies(target['method']))
                    row.update(target_cache[target['method']])
                    if not target['selected_original_Code']:
                        row['gaps'].append('Original static target Code is not selected in current Source')
                    if not target['provided_backend_body']:
                        row['gaps'].append('Original static target backend body is not provided')
                    row['gaps'].extend(g['reason'] for g in row['Unsafe_dependencies']['source_gaps'])
                    native = row['Unsafe_dependencies']['native_terminals']
                    missing_native = [t['method'] for t in native if not t['selected_Unsafe_memory_catalog_entry']]
                    if missing_native:
                        row['gaps'].append('Unsafe native terminal lacks current selected memory-catalog entry: '+','.join(map(str,missing_native)))
                    row['status'] = 'source_ready_only_not_runtime_acceptance' if not row['gaps'] else 'source_or_dependency_gap'
                dispatch.append(row)
        # Independently check original CP and selected/provided caller Code for
        # every currently diagnosed VarHandle signature-polymorphic call site.
        declaration_ids = {row['method'] for row in native_declarations}
        candidates = [dict(row_id=row['id'],binding=row['binding'],source_sha256=row.get('source_sha256')) for row in diagnostic['rows']
                      if row.get('binding') and row['binding'].get('kind')=='signature_polymorphic_native' and row['binding'].get('resolved_method') in declaration_ids]
        wanted_ids = {row['binding']['caller_class'] for row in candidates}
        for row in all_classes:
            if row['id'] in wanted_ids and row['name'] not in raws:
                classes[row['name']]=row;add_class(row)
        by_id = {row['id']:row for row in classes.values()}
        sites = []
        for entry in candidates:
            binding = entry['binding']
            cls = by_id[binding['caller_class']]
            raw = raws[cls['name']]
            member = raw.member(binding['constant'])
            check(entry['source_sha256']==cls['origin']['sha256'] and binding['opcode']==182,
                  'Original diagnostic Class hash/opcode differs')
            check(member['owner']=='java/lang/invoke/VarHandle' and member['name'] in mode_names and member['descriptor']==binding['descriptor'], 'Original signature-polymorphic CP differs from diagnostic binding')
            check(native_by_name[member['name']]['method']==binding['resolved_method'], 'Original native declaration resolution differs')
            occurrences = []
            for mid in cls['method_ids']:
                if not methods[mid]['selected_original_Code']:
                    continue
                method = raw.methods[cls['method_ids'].index(mid)]
                code = raw.code(method)
                if code:
                    for ins in I.stream(code['bytes']):
                        if ins['opcode']==binding['opcode'] and int.from_bytes(code['bytes'][ins['pc']+1:ins['pc']+3],'big')==binding['constant']:
                            occurrences.append(dict(method=mid,pc=ins['pc'],code_sha256=methods[mid]['code_sha256'],provided_backend_body=methods[mid]['provided_backend_body']))
            sites.append(dict(**entry,operation=member['name'],original_CP_member=member,caller_class_name=cls['name'],selected_original_occurrences=occurrences))
        return dict(original_signature_polymorphic_declarations=native_declarations,actual_AccessModes=modes,
                    runtime_families=families,dispatch_candidates=dispatch,selected_original_CP_sites=sites,
                    source_presence_is_not_runtime_domain_or_execution_acceptance=True)
    finally:reader.close()


def index(summary,classes,selection,diagnostic,layouts,frame,abi=None):
    """Activate source-derived same-primitive instance comparison shapes only."""
    abi=read(ABI_FILE) if abi is None else abi
    expected_ops={'compareAndSet':1,'weakCompareAndSetPlain':2,'weakCompareAndSet':3,
                  'weakCompareAndSetAcquire':4,'weakCompareAndSetRelease':5}
    check(abi['schema']==1 and abi['service']=='boom_varhandle_primitive_compare' and abi['pool']=='boom_varhandle_primitive_pool' and
          abi['context_bytes']==32 and abi['operations']==expected_ops and abi['wire_kinds']=={'I':1,'J':2} and
          abi['pool_layout']['bytes']==192 and abi['pool_layout']['abi']==1 and int(abi['pool_layout']['magic'],0)==0x50435056 and
          abi['site64']['reserved_zero_Q40_Q48_Q56']==40 and abi['dispatch80']['reserved_Q72']==72 and len(abi['argv_QWORD_slots'])==4 and
          abi['active_runtime_families']==['java/lang/invoke/VarHandleInts$FieldInstanceReadWrite','java/lang/invoke/VarHandleLongs$FieldInstanceReadWrite'],
          'Unsupported primitive comparison source/dispatch ABI')
    C,I=module('constructor-provider-source'),module('verify-translation-ir')
    # Rebuild the existing reference contract from its permanent source API;
    # no prior candidate, directory JSON, output artifact or epoch is consumed.
    reference=module('varhandle-reference-cas-source').index(summary,classes,selection,diagnostic,layouts,frame)
    directory=field_directory(summary,classes,selection,diagnostic,layouts,frame,reference['dispatch'][0]['runtime_class'])
    types,_,_,resolve=C.inputs(summary,classes);kinds={t['id']:t['kind'] for t in types}
    chosen={c['class_id']:c for c in selection['selected_classes']}
    reader=C.RawClasses(summary);raws={}
    def raw_class(ident):
        if ident not in raws:
            cls=classes[ident];data=reader.read(cls);raw=I.Source(data)
            check(hashlib.sha256(data).hexdigest()==cls['origin']['sha256'] and raw.name==cls['name'] and len(raw.methods)==len(cls['method_ids']),
                  'Original raw Class/declaration order differs')
            raws[ident]=raw
        return raws[ident]
    try:
        declarations={r['name']:r for r in directory['original_signature_polymorphic_declarations']}
        sites=[]
        for entry in directory['selected_original_CP_sites']:
            if entry['operation'] not in abi['operations']:continue
            b=entry['binding']
            if str(b['caller_method']) not in selection['selected_methods']:continue
            shape=re.fullmatch(r'\((L[^;]+;|\[+(?:L[^;]+;|[ZBCSIJFD]))([IJ])\2\)Z',b['descriptor'])
            if shape is None:continue
            cls=classes[b['caller_class']];raw=raw_class(cls['id']);cp=raw.member(b['constant']);decl=declarations[entry['operation']]
            check(b['opcode']==182 and b['resolved_method']==decl['method'] and decl['code_sha256'] is None and decl['access']&0x180==0x180 and
                  cp['owner']=='java/lang/invoke/VarHandle' and cp['name']==entry['operation'] and cp['descriptor']==b['descriptor'],
                  'Original primitive CP/declaration differs')
            occurrences=[]
            for mid,method in zip(cls['method_ids'],raw.methods):
                selected=selection['selected_methods'].get(str(mid))
                if selected is None:continue
                code=raw.code(method)
                check(code and I.digest(code['bytes'])['sha256']==selected['code_sha256'] and selected['source_sha256']==cls['origin']['sha256'],
                      'Original selected caller Code differs')
                for ins in I.stream(code['bytes']):
                    if ins['opcode']==182 and ins['operand']['Constant']==b['constant']:
                        body=selection['selected_function_sha256'].get('boom_m'+str(mid)+'_body')
                        check(body,'Original selected caller body not provided')
                        occurrences.append(dict(method=mid,pc=ins['pc'],code_sha256=selected['code_sha256'],provided_backend_body_sha256=body))
            check(any(o['method']==b['caller_method'] for o in occurrences),'Original selected caller lacks this CP site')
            descriptors=[shape[1],shape[2],shape[2]];ids=[resolve(cls['origin']['loader'],d) for d in descriptors]
            check(all(i is not None for i in ids) and kinds[ids[0]] in (1,2,3) and kinds[ids[1]]==kinds[ids[2]]==0,'Source coordinate TYPEs differ')
            sites.append(dict(**b,row=entry['row_id'],index=len(sites),operation_name=entry['operation'],operation=abi['operations'][entry['operation']],
                              original_CP_member=cp,original_Class_sha256=cls['origin']['sha256'],original_selected_occurrences=occurrences,
                              original_caller_selected=True,argument_descriptors=descriptors,argument_type_ids=ids,primitive_wire=abi['wire_kinds'][shape[2]]))
        check(sites and len(sites)==len({s['label'] for s in sites}),'Empty or duplicate original primitive sites')
        families={f['runtime_class_name']:f for f in directory['runtime_families']};dispatch=[]
        for row in directory['dispatch_candidates']:
            if row['operation'] not in abi['operations'] or row['runtime_class_name'] not in abi['active_runtime_families']:continue
            check(row['status']=='source_ready_only_not_runtime_acceptance' and not row['gaps'] and row['storage']=='Instance' and row['mutability']=='ReadWrite',
                  'Original active family/static target unavailable')
            target=row['target'];cid=target['class_id'];raw=raw_class(cid)
            check(chosen.get(row['runtime_class'],{}).get('diagnostic','unselected') is None and
                  chosen[row['runtime_class']]['source_sha256']==classes[row['runtime_class']]['origin']['sha256'],
                  'Active original runtime family Class is not selected normally')
            mid,method=next((mid,m) for mid,m in zip(classes[cid]['method_ids'],raw.methods) if (m['name'],m['descriptor'])==(target['name'],target['descriptor']))
            code=raw.code(method)
            check(mid==target['method'] and code and I.digest(code['bytes'])['sha256']==target['code_sha256'] and target['access']&8 and
                  target['selected_original_Code']==selection['selected_methods'].get(str(mid)) and target['provided_backend_body'] and
                  target['provided_backend_body']==selection['selected_function_sha256'].get(target['normal_symbol']+'_body'),
                  'Original static target Code/backend body differs')
            primitive={'Ints':'I','Longs':'J'}[row['value_family']]
            check(target['descriptor']=='(Ljava/lang/invoke/VarHandle;Ljava/lang/Object;'+primitive*2+')Z','Original primitive static target shape differs')
            for terminal in row['Unsafe_dependencies']['native_terminals']:
                check(terminal['selected_Unsafe_memory_catalog_entry']==selection['selected_Unsafe_memory_natives'].get(str(terminal['method'])),
                      'Existing Unsafe primitive provider source differs')
            family=families[row['runtime_class_name']];exact=next(f for f in family['instance_field_bindings'] if f['name']=='exact')
            receiver=row['field_layout_bindings']['receiver_type'];offset=row['field_layout_bindings']['field_offset']
            value_type=resolve('bootstrap',primitive)
            check(exact['descriptor']=='Z' and exact['storage_bytes']==1 and receiver['descriptor']=='Ljava/lang/Class;' and offset['descriptor']=='J' and value_type is not None,
                  'Original VarHandle fields/primitive TYPE differ')
            dispatch.append(dict(operation=abi['operations'][row['operation']],operation_name=row['operation'],runtime_class=row['runtime_class'],
                                 target=target['normal_symbol'],layout='boom_layout'+str(row['runtime_class']),exact=exact['FMAPPROC_symbol'],
                                 receiver=receiver['FMAPPROC_symbol'],field_offset=offset['FMAPPROC_symbol'],primitive_type_id=value_type,
                                 primitive_wire=abi['wire_kinds'][primitive],source_directory_row=row,source_family=family))
        dispatch.sort(key=lambda row:(row['operation'],row['runtime_class']))
        check(len(dispatch)==len(abi['operations'])*len(abi['active_runtime_families']),'Active operation/family product incomplete')
        check(not {r['label'] for r in sites}.intersection(r['label'] for r in reference['sites']),'Primitive source labels redefine existing reference sites')
        symbols={k:reference['symbols'][k] for k in ('heap_cell','runtime_map','class_pool','WMT_class','WMT_layout','WMT_ctor','Throwable_type')}
        return dict(schema=1,ABI=abi,sites=sites,dispatch=dispatch,symbols=symbols,source_field_directory=directory,
                    original_WMT_constructor=reference['original_WMT_constructor'],existing_reference_CAS_sites=reference['sites'],
                    reference_labels_not_redefined=True,additional_oop_roots=[],registered_pack=False,
                    original_Java_Code_or_native_Frame_modified=False,complete_VarHandle_or_MethodHandle_support=False,Java_or_Main_executed=False)
    finally:reader.close()


def render(model,fragment=None):
    """Emit two normal Win64 source units without assembling or running them."""
    sites=model['sites'];symbols=model['symbols'];dispatch=model['dispatch']
    native=['option casemap:none','EXTERN boom_varhandle_primitive_compare:PROC','EXTERN boom_varhandle_primitive_pool:BYTE','EXTERN boom_varhandle_primitive_sites:BYTE']
    for site in sites:
        n=site['label'];native+=['PUBLIC '+n,'.code',n+' PROC FRAME',' .endprolog',' lea r8,boom_varhandle_primitive_pool',
            ' lea r9,boom_varhandle_primitive_sites+'+str(site['index']*64),' jmp boom_varhandle_primitive_compare',n+' ENDP']
    native+=['END','']
    imports={n:'PROC' for n in ('boom_heap_contains','boom_runtime_row','boom_object_check','boom_java_class_typeid','boom_class_ensure32','boom_object_new','boom_exception_set32')}
    imports.update({s:('PROC' if k=='WMT_ctor' else 'BYTE') for k,s in symbols.items()})
    for row in dispatch:
        imports.update({row[k]:('BYTE' if k=='layout' else 'PROC') for k in ('target','layout','exact','receiver','field_offset')})
    service=['option casemap:none',*['EXTERN '+n+':'+kind for n,kind in sorted(imports.items())],
        'PUBLIC boom_varhandle_primitive_pool','PUBLIC boom_varhandle_primitive_sites','PUBLIC boom_varhandle_primitive_dispatch','.const','ALIGN 8',
        'boom_varhandle_primitive_pool DWORD 050435056h,1,192,'+str(len(sites)),
        ' QWORD '+','.join(symbols[k] for k in ('heap_cell','runtime_map','class_pool')),
        ' QWORD boom_varhandle_primitive_sites,boom_varhandle_primitive_dispatch',' DWORD '+str(len(dispatch))+',64,80,4',
        ' QWORD '+','.join(symbols[k] for k in ('WMT_class','WMT_layout','WMT_ctor','Throwable_type')),' QWORD 11 DUP(0)',
        'ALIGN 8','boom_varhandle_primitive_sites LABEL BYTE']
    for site in sites:
        service+=[' DWORD '+','.join(str(n) for n in [site['caller_class'],site['constant'],site['opcode'],site['operation'],*site['argument_type_ids'],1,site['primitive_wire'],4]),' QWORD 3 DUP(0)']
    service+=['ALIGN 8','boom_varhandle_primitive_dispatch LABEL BYTE']
    for row in dispatch:
        service+=[' DWORD '+str(row['operation'])+','+str(row['runtime_class']),
            ' QWORD '+','.join(row[k] for k in ('target','layout','exact','receiver')),
            ' DWORD '+str(row['primitive_type_id'])+','+str(row['primitive_wire'])+',3,1,1,0',' QWORD '+row['field_offset']+',0']
    service+=[FRAGMENT.read_text(encoding='utf-8') if fragment is None else fragment,'END','']
    return dict(zip(('varhandle-primitive-cas-sites','varhandle-primitive-cas-service'),('\n'.join(native),'\n'.join(service))))


def project(summary_file,classes_file,selection_file,diagnostic_file,layouts_file,frame_file,source_verification,abi=None):
    paths=[Path(p).resolve() for p in (summary_file,classes_file,selection_file,diagnostic_file,layouts_file,frame_file)]
    summary,selection,diagnostic,frame=[read(paths[i]) for i in (0,2,3,5)]
    # Validate explicit namespace/source identities before the source index is built.
    check(selection['source_batch_summary_sha256']==artifact(paths[0])['digest']['sha256'] and
          selection['source_classes_sha256']==artifact(paths[1])['digest']['sha256'] and paths[4]==checked(summary['layouts']),
          'Explicit original summary/classes/layout identities differ')
    check(paths[3]==(paths[2].parent/selection['diagnostic_manifest']).resolve() and
          paths[5]==checked(selection['runtime_frame_overlay']['reference']['manifest']),
          'Explicit original diagnostic/Frame input identity differs')
    proof=Path(source_verification).resolve();value=read(proof)
    check(value['verified'] and value['closure_manifest_sha256']==artifact(paths[2])['digest']['sha256'],
          'Existing complete Source verification differs')
    classes=[json.loads(line) for line in paths[1].open(encoding='utf-8')]
    layouts=[json.loads(line) for line in paths[4].open(encoding='utf-8')]
    metadata=index(summary,classes,selection,diagnostic,layouts,frame,abi=abi)
    metadata.update(source_manifest=artifact(paths[2]),source_full_verification=artifact(proof),
                    original_source_inputs=[artifact(p) for p in paths],
                    original_auxiliary_inputs=[summary['unsafe_fields']['index'],summary['runtime_metadata']['index']])
    return metadata


def main(args):
    output=args.output.resolve()
    check(any(output.is_relative_to((ROOT/name).resolve()) for name in ('.boom','target','dist')),
          'Output must stay in project .boom, target or dist')
    check(not output.exists(),'Fresh source-only output required')
    metadata=project(args.summary,args.classes,args.selection,args.diagnostic,args.layouts,args.frame,args.source_verification)
    output.mkdir(parents=True)
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    for role,text in render(metadata).items():(output/(role+'.asm')).write_text(text,encoding='utf-8',newline='\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('summary','classes','selection','diagnostic','layouts','frame','source-verification','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    main(parser.parse_args())
