"""Independent normal Reference.get0 source model, without NIO dependencies."""
import hashlib
import json
import re
import zipfile


OWNER='java/lang/ref/Reference'
POOL='boom_provider_reference_referent_pool'
SERVICE='boom_provider_reference_referent_get'
CONTROL=set()
FOREIGN=set()
KERNELS=['heap.asm','objects.asm','field_address.asm','runtime_types.asm','runtime_type_index.asm',
         'types.asm','classes32.asm','frames.asm']
POLICY=dict(normal_source_layouts=True,inherited_referent_FMAP=True,heap_nonmoving=True,
    collection_requires_quiescence=True,aligned_reference_load=True,existing_exception_preserved=True,
    automatic_reference_discovery=False,weak_reference_GC_complete=False,
    class_redefinition_supported=False,source_transform_chain='original_locked_no_transforms')


def normalized_kernel(text,original=False):
    name='boom_source_reference_get' if original else SERVICE
    text=text.replace(name,'REFERENCE_READER').replace('rget_' if original else 'refget_','reader_')
    return '\n'.join(line.split(';',1)[0].strip() for line in text.splitlines() if line.split(';',1)[0].strip())


def index(summary,classes,S):
    [owner]=[c for c in classes if c['name']==OWNER and c['origin']['loader']=='bootstrap']
    S.check(owner['access']==0x421 and owner['origin']['source_id']=='jdk:java.base' and not owner['origin'].get('generated'),
            'Original abstract bootstrap Reference required')
    I=S.module('normal_referent_original_class','verify-translation-ir.py')
    raw=I.Source(S.original_class(summary,owner))
    S.check(raw.name==OWNER and len(raw.methods)==len(owner['method_ids']) and
            [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]==owner['fields'],
            'Original Reference method/field inventory differs')
    members={(m['name'],m['descriptor']):(i,m,raw.code(m)) for i,m in zip(owner['method_ids'],raw.methods)}
    native,decl,code=members['get0','()Ljava/lang/Object;']
    S.check(decl['access']==0x102 and code is None,'Original private instance Reference.get0 declaration differs')
    getter,m,body=members['get','()Ljava/lang/Object;']
    calls=[(instruction['pc'],raw.member(instruction['operand']['Constant'])) for instruction in I.stream(body['bytes'])
           if instruction['opcode'] in (0xb6,0xb7)]
    S.check(m['access']==1 and len(calls)==1 and
            (calls[0][1]['owner'],calls[0][1]['name'],calls[0][1]['descriptor'])==(OWNER,'get0','()Ljava/lang/Object;'),
            'Ordinary original Reference.get does not call this exact native')
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
    tested=S.ROOT/'native/providers/reference_referent_read.asm.inc'
    standalone=S.ROOT/'native/providers/reference_referent_get.asm.inc'
    S.check(normalized_kernel(tested.read_text(),True)==normalized_kernel(standalone.read_text()),
            'Standalone Reference reader changed a tested instruction or branch')
    method=dict(method=native,class_id=owner['id'],class_sha256=owner['origin']['sha256'],loader='bootstrap',
        source_id='jdk:java.base',owner=OWNER,name='get0',descriptor='()Ljava/lang/Object;',access=0x102,operation=0)
    return dict(schema=1,owner=owner['id'],methods=[method],referent_field=field,
        ordinary_Java_get=dict(method=getter,owner=OWNER,name='get',descriptor='()Ljava/lang/Object;',
            code_sha256=hashlib.sha256(body['bytes']).hexdigest(),native_call_pc=calls[0][0]),
        required_classes=[owner['id']],required_base_modules=['runtime_metadata'],required_provider_families=[],
        pool_bytes=24,pool_abi=1,normal_source_heap=True,inherited_receiver_count=len(needed),
        tested_reader=S.artifact(tested),normalization='service and private branch labels only; instructions unchanged')


def data(meta):
    return (f'.const\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 054454752h,1\n'
            f" QWORD OFFSET boom_heap_ptr,OFFSET boom_field_map{meta['referent_field']['id']}\n")


def native_imports(meta):
    return ({'boom_heap_contains','boom_trace_enter','boom_trace_leave',f"boom_field_map{meta['referent_field']['id']}"},
            {'boom_heap_ptr','boom_trace_pool',f"boom_trace_method{meta['methods'][0]['method']}"})
