"""Source and normal heap metadata for BootLoader's single native module publication."""
import hashlib
import json
import zipfile


OWNER='jdk/internal/loader/BootLoader'
MOD='java/lang/Module'
JLA='jdk/internal/access/JavaLangAccess'
MODULE='Ljava/lang/Module;'
LOADER='Ljava/lang/ClassLoader;'
POOL='boom_java_class_pool'
SERVICE='boom_boot_unnamed_normal'
CONTROL=set()
FOREIGN={'GetCurrentThreadId'}
KERNELS=['java_classes.asm','classes32.asm','frames.asm','heap.asm','objects.asm',
         'runtime_types.asm','runtime_type_index.asm','types.asm']
POLICY=dict(identity='source_BootLoader_UNNAMED_MODULE',publication='existing_JCLS_GC_root',
            same_reference_required=True,bootstrap_loader_key=0,duplicate_Module_allocation=False)


def index(summary,classes,S):
    ir=S.module('boot_unnamed_classfile','verify-translation-ir.py')
    field_model=S.module('boot_unnamed_field_layout','file-bootstrap-source.py')
    specs=[(OWNER,'<clinit>','()V'),('java/lang/System$2','defineUnnamedModule','('+LOADER+')'+MODULE),
           (MOD,'<init>','('+LOADER+')V'),('java/lang/System$2','addEnableNativeAccess','('+MODULE+')'+MODULE),
           (MOD,'implAddEnableNativeAccess','()'+MODULE),(MOD+'$EnableNativeAccess','trySetEnableNativeAccess','('+MODULE+')Z')]
    native_key=(OWNER,'setBootLoaderUnnamedModule0','('+MODULE+')V')
    owners={c['name']:c for c in classes if c['origin']['loader']=='bootstrap' and c['name'] in {s[0] for s in specs}}
    java,source={},{}
    for owner,c in owners.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),'Original java.base class required')
        raw=ir.Source(S.original_class(summary,c))
        S.check(raw.name==owner and len(c['method_ids'])==len(raw.methods) and
                [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],'Original class inventory differs')
        source[owner]=raw
        for method,m in zip(c['method_ids'],raw.methods):
            key=(owner,m['name'],m['descriptor'])
            if key not in specs and key!=native_key:continue
            S.check(key not in java,'Ambiguous source member')
            java[key]=(method,m,raw.code(m))
    S.check(set(java)==set(specs)|{native_key},'Original module source chain is incomplete')
    boot=owners[OWNER];module=owners[MOD]
    method,native,code=java[native_key]
    S.check(native['access']==0x10a and code is None,'Expected private static native void(Module)')
    method_row=dict(method=method,class_id=boot['id'],class_sha256=boot['origin']['sha256'],loader='bootstrap',
        owner=OWNER,source_id='jdk:java.base',name=native_key[1],descriptor=native_key[2],access=native['access'],operation=0)
    [static]=[i for i,f in enumerate(source[OWNER].fields) if f==dict(name='UNNAMED_MODULE',descriptor=MODULE,access=0x1a,
                                                                       constant_value=None)]
    members=[]
    for key in specs:
        mid,record,code=java[key]
        S.check(code is not None and not record['access']&0x500,'Original method must have executable Java bytecode')
        members.append(dict(method=mid,owner=key[0],name=key[1],descriptor=key[2],class_sha256=owners[key[0]]['origin']['sha256'],
                            code_sha256=hashlib.sha256(code['bytes']).hexdigest()))
    clinit=java[specs[0]][2]['bytes']
    by_pc={i['pc']:i for i in ir.stream(clinit)}
    sites=[(18,0xb9,JLA,'defineUnnamedModule',specs[1][2]),(23,0xb3,OWNER,'UNNAMED_MODULE',MODULE),
           (27,0xb2,OWNER,'UNNAMED_MODULE',MODULE),(30,0xb9,JLA,'addEnableNativeAccess',specs[3][2]),
           (36,0xb2,OWNER,'UNNAMED_MODULE',MODULE),(39,0xb8,*native_key)]
    S.check(by_pc[17]['opcode']==1 and by_pc[59]['opcode']==0xb1,'Original bootstrap null loader or return changed')
    for pc,opcode,owner,name,descriptor in sites:
        i=by_pc[pc]
        cp=i['operand']['Interface']['constant'] if opcode==0xb9 else i['operand']['Constant']
        ref=source[OWNER].member(cp)
        S.check(i['opcode']==opcode and (ref['owner'],ref['name'],ref['descriptor'])==(owner,name,descriptor),
                'Original module creation, storage or native callsite changed')
    with zipfile.ZipFile(S.checked(summary['class_state']['index'])) as z, z.open('classes.jsonl') as lines:
        state=next(row for line in lines if (row:=json.loads(line))['class_id']==boot['id'])
    cell=next(f for f in state['fields'] if f['index']==static)
    S.check(state['source_sha256']==method_row['class_sha256'] and state['initializer']==dict(method=members[0]['method'],
        code_sha256=members[0]['code_sha256'],assembly_emitted=True) and (cell['name'],cell['descriptor'],cell['access'])==
        ('UNNAMED_MODULE',MODULE,0x1a) and cell['reference'] and cell['declared_storage_bytes']==8 and
        cell['initial_bits']==0 and cell['constant'] is None,'Normal BootLoader initializer or static GC root differs')
    specs_fields=[('layer','Ljava/lang/ModuleLayer;',0x12,8,True),('name','Ljava/lang/String;',0x12,8,True),
                  ('loader',LOADER,0x12,8,True),('descriptor','Ljava/lang/module/ModuleDescriptor;',0x12,8,True),
                  ('enableNativeAccess','Z',2,1,False)]
    with S.checked(summary['layouts']).open(encoding='utf-8') as lines:
        layout=next(row for line in lines if (row:=json.loads(line))['class_id']==module['id'])
    fields=field_model.fields(module,layout,specs_fields,S)
    jcls=summary['class_literals']
    roots=jcls['modules']
    slot=jcls.get('bootstrap_unnamed_module_slot')
    S.check(type(slot) is int and 0<=slot<len(roots) and jcls['loader_keys'][0]=='bootstrap' and
            [m['id'] for m in roots if m['loader']==0 and m['name'] is None]==[slot] and
            [r['id'] for r in roots]==list(range(len(roots))) and jcls['root_cells']==jcls['type_capacity']+
            len(jcls['loader_keys'])+len(roots) and jcls['source_shape']['module_type']==module['id'],
            'Verified normal JCLS pool with one explicit bootstrap unnamed slot required')
    return dict(schema=1,owner=boot['id'],methods=[method_row],original_java=members,static_field=static,
                module_class=module['id'],module_fields=fields,slot=slot,module_count=len(roots),strong_roots=jcls['root_cells'],
                required_classes=sorted(c['id'] for c in owners.values()),required_java_methods=[m['method'] for m in members],
                required_base_modules=['class_literals'],required_provider_families=[],pool_bytes=144,pool_abi=1)


def native_imports(meta):
    [native]=meta['methods']
    procs={'boom_trace_enter','boom_trace_leave','boom_java_class_bind_module','boom_heap_contains','boom_object_check',
           'GetCurrentThreadId'}
    data={POOL,'boom_heap_ptr','boom_trace_pool',f"boom_layout{meta['module_class']}",
          f"boom_s{meta['owner']}_{meta['static_field']}",f"boom_trace_method{native['method']}"}
    return procs,data


def data(meta):
    owner=meta['owner']
    header=(f"BUN_OWNER TEXTEQU <boom_class{owner}>\nBUN_STATIC TEXTEQU <boom_s{owner}_{meta['static_field']}>\n"
            f"BUN_LAYOUT TEXTEQU <boom_layout{meta['module_class']}>\nBUN_SLOT EQU {meta['slot']}\n"
            f"BUN_MODULES EQU {meta['module_count']}\n")
    names={'layer':'LAYER','name':'NAME','loader':'LOADER','descriptor':'DESCRIPTOR','enableNativeAccess':'ENABLE'}
    return header+''.join(f"BUN_{names[f['name']]} EQU {f['offset']}\n" for f in meta['module_fields'])
