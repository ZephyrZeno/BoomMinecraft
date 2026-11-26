"""Original normal Reference get/identity/clear and Phantom identity source model."""
import hashlib
import json
import re
import zipfile


OWNER='java/lang/ref/Reference'
PHANTOM='java/lang/ref/PhantomReference'
FINAL='java/lang/ref/FinalReference'
POOL='boom_provider_reference_referent_pool'
SERVICE='boom_provider_reference_referent_get'
CONTROL=set()
FOREIGN=set()
KERNELS=['heap.asm','objects.asm','field_address.asm','runtime_types.asm','runtime_type_index.asm',
         'types.asm','classes32.asm','frames.asm']
POLICY=dict(normal_source_layouts=True,inherited_referent_FMAP=True,heap_nonmoving=True,
    collection_requires_quiescence=True,aligned_reference_load=True,existing_exception_preserved=True,
    atomic_clear='xchg_aligned_reference',identity_uses_single_snapshot=True,clear_does_not_enqueue=True,
    concurrent_reference_processing=False,concurrent_GC_barriers=False,referent_fields_traced_strongly=True,
    automatic_reference_discovery=False,weak_reference_GC_complete=False,
    class_redefinition_supported=False,source_transform_chain='original_locked_no_transforms')


SPECS=[(OWNER,'get0','()Ljava/lang/Object;',0),(OWNER,'refersTo0','(Ljava/lang/Object;)Z',1),
       (OWNER,'clear0','()V',2),(PHANTOM,'refersTo0','(Ljava/lang/Object;)Z',3)]
PINS={'jvm.cpp':'84436b103fb7869e445bac95d2e82e9de9160c2da327a4cf54f4e84555150ad9',
      'Reference.c':'f56c77e560530c747d9af26e907e051d7c49a36ca6360d75ca3e803a7cae0e90',
      'PhantomReference.c':'a0d730a87699e31a137079f45f1c3d91c0e2e33ce29e269b6357a38704d7b661',
      'javaClasses.inline.hpp':'954c5f971f3b7ee52b4572c3bf9b072d9ac2908478caa777291048efa3326ce5'}


def index(summary,classes,S):
    names={c['name']:c for c in classes if c['name'] in (OWNER,PHANTOM,FINAL) and c['origin']['loader']=='bootstrap'}
    S.check(set(names)=={OWNER,PHANTOM,FINAL},'Original reference classes are missing')
    owner=names[OWNER]
    S.check(owner['access']==0x421 and owner['origin']['source_id']=='jdk:java.base' and not owner['origin'].get('generated'),
            'Original abstract bootstrap Reference required')
    I=S.module('normal_referent_original_class','verify-translation-ir.py')
    members={};parsed={}
    for name,c in names.items():
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated'),
            'Original bootstrap Reference class required')
        raw=I.Source(S.original_class(summary,c));parsed[name]=raw
        S.check(raw.name==name and len(raw.methods)==len(c['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==c['fields'],
            'Original Reference method/field inventory differs')
        members.update({(name,m['name'],m['descriptor']):(i,m,raw.code(m)) for i,m in zip(c['method_ids'],raw.methods)})
    methods=[]
    for name,method,descriptor,operation in SPECS:
        ident,decl,code=members[name,method,descriptor]
        S.check(decl['access']==0x102 and code is None,'Original private instance reference native declaration differs')
        c=names[name]
        methods.append(dict(method=ident,class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
            source_id='jdk:java.base',owner=name,name=method,descriptor=descriptor,access=0x102,operation=operation))
    java=[]
    links=[(OWNER,'get','()Ljava/lang/Object;',1,OWNER,'get0'),
        (OWNER,'refersTo','(Ljava/lang/Object;)Z',0x11,OWNER,'refersToImpl'),
        (OWNER,'refersToImpl','(Ljava/lang/Object;)Z',0,OWNER,'refersTo0'),
        (OWNER,'clear','()V',1,OWNER,'clear0'),
        (PHANTOM,'refersToImpl','(Ljava/lang/Object;)Z',0,PHANTOM,'refersTo0')]
    for name,method,descriptor,access,target_owner,target in links:
        ident,m,body=members[name,method,descriptor]
        calls=[(op['pc'],parsed[name].member(op['operand']['Constant'])) for op in I.stream(body['bytes'])
               if op['opcode'] in (0xb6,0xb7,0xb8,0xb9)]
        S.check(m['access']==access and len(calls)==1 and
            (calls[0][1]['owner'],calls[0][1]['name'],calls[0][1]['descriptor'])==(target_owner,target,descriptor),
            'Original reference Java delegation changed')
        java.append(dict(method=ident,owner=name,class_id=names[name]['id'],class_sha256=names[name]['origin']['sha256'],
            name=method,descriptor=descriptor,access=access,code_sha256=hashlib.sha256(body['bytes']).hexdigest(),
            target_owner=target_owner,target=target,call_pc=calls[0][0]))
    ident,m,body=members[PHANTOM,'get','()Ljava/lang/Object;']
    S.check(m['access']==1 and body['bytes']==b'\x01\xb0','Original PhantomReference.get must return null in Java')
    java.append(dict(method=ident,owner=PHANTOM,class_id=names[PHANTOM]['id'],class_sha256=names[PHANTOM]['origin']['sha256'],
        name='get',descriptor='()Ljava/lang/Object;',access=1,code_sha256=hashlib.sha256(body['bytes']).hexdigest(),returns_null=True))
    [field_index]=[i for i,f in enumerate(owner['fields']) if f==dict(name='referent',descriptor='Ljava/lang/Object;',access=2)]
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        [field]=[r for line in archive.open('fields.jsonl') if (r:=json.loads(line))['declaring_class']==owner['id'] and
                 r['declaring_field']==field_index]
        needed={r['receiver_class'] for r in field['rows']}
        types={r['id']:r for line in archive.open('types.jsonl') if (r:=json.loads(line))['id'] in needed}
    S.check(field['reference'] is True and field['storage_bytes']==8 and
            len(needed)==len(field['rows']) and owner['id'] in needed and set(types)==needed,
            'Original referent field map identity/domain differs')
    owners={c['id']:c for c in classes}
    layouts={}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['class_id'] in needed:
                layouts[row['class_id']]=row
    S.check(set(layouts)==needed,'Inherited Reference layouts are incomplete')
    for row in field['rows']:
        ident,offset=row['receiver_class'],row['offset']
        S.check(types[ident]['kind']==1 and types[ident]['source_sha256']==owners[ident]['origin']['sha256'] and
                (ident==owner['id'] or owner['id'] in types[ident]['ancestors']) and
                layouts[ident]['diagnostic'] is None and layouts[ident]['source_sha256']==owners[ident]['origin']['sha256'] and
                offset%8==0 and offset+8<=layouts[ident]['candidate']['payload_bytes'] and
                offset<layouts[ident]['candidate']['reference_prefix']*8 and any(
                    f['member']['owner']==owner['id'] and f['member']['index']==field_index and
                    f['offset']==offset and f['reference'] and f['storage_bytes']==8
                    for f in layouts[ident]['candidate']['fields']),
                'Inherited normal Reference receiver type/layout differs')
    S.check(all(names[name]['id'] in needed for name in (PHANTOM,FINAL)),
        'Phantom/Final reference types must use the inherited referent field')
    pinned=S.ART/'reference-referent/pinned-sources/jdk-21.0.13+3'
    native_sources={name:S.artifact(pinned/name) for name in PINS}
    S.check(all(r['digest']['sha256']==PINS[name] for name,r in native_sources.items()),'Pinned reference native semantics changed')
    return dict(schema=2,owner=owner['id'],methods=methods,referent_field=field,ordinary_Java=java,
        phantom_type=names[PHANTOM]['id'],final_reference_type=names[FINAL]['id'],
        required_classes=sorted(c['id'] for c in names.values()),required_base_modules=['runtime_metadata'],
        required_provider_families=[],required_java_methods=[],pool_bytes=48,pool_abi=2,
        normal_source_heap=True,inherited_receiver_count=len(needed),native_sources=native_sources,
        original_get_reader=S.artifact(S.ROOT/'native/providers/reference_referent_read.asm.inc'))


def data(meta):
    return (f'.const\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 054454752h,2\n'
            f" QWORD OFFSET boom_heap_ptr,OFFSET boom_field_map{meta['referent_field']['id']}\n"
            f" QWORD OFFSET boom_runtime_type_map,OFFSET boom_t{meta['phantom_type']},OFFSET boom_t{meta['final_reference_type']}\n")


def native_imports(meta):
    return ({'boom_heap_contains','boom_runtime_type','boom_type_assignable','boom_trace_enter','boom_trace_leave',
             f"boom_field_map{meta['referent_field']['id']}"},
            {'boom_heap_ptr','boom_trace_pool','boom_runtime_type_map',f"boom_t{meta['phantom_type']}",
             f"boom_t{meta['final_reference_type']}"}|{f"boom_trace_method{m['method']}" for m in meta['methods']})
