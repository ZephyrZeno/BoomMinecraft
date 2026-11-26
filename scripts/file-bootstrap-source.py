"""Original file stream/descriptor native contracts and normal field tables."""
import importlib.util
import json
from pathlib import Path


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


R=module('file_bootstrap_original_parser','verify-batch-frames.py')
SPECS=(('java/io/FileInputStream','initIDs','()V',0),('java/io/FileOutputStream','initIDs','()V',1),
       ('java/io/FileDescriptor','initIDs','()V',2),('java/io/FileDescriptor','getHandle','(I)J',3),('java/io/FileDescriptor','getAppend','(I)Z',4),
       ('java/lang/StringUTF16','isBigEndian','()Z',5))
KERNELS=['classes32.asm','objects.asm','file_streams.asm','file_descriptors.asm']


def contracts(summary,classes,S):
    names={(c['origin']['loader'],c['name']):c for c in classes};raw={};result=[]
    for owner,name,desc,op in SPECS:
        c=names['bootstrap',owner]
        expected_access=0 if owner=='java/lang/StringUTF16' else 1
        S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated') and c['access']&0x601==expected_access,
                'File/byte-order native needs its original bootstrap declaring class')
        if owner=='java/lang/StringUTF16':S.check(c['access']&0x10,'StringUTF16 must retain its original final class contract')
        if owner not in raw:
            actual,methods=R.original_methods(S.original_class(summary,c));S.check(actual==owner and len(methods)==len(c['method_ids']),'File original method inventory differs');raw[owner]=methods
        found=[(i,m) for i,m in zip(c['method_ids'],raw[owner]) if (m['name'],m['descriptor'])==(name,desc)]
        S.check(len(found)==1 and found[0][1]['access']==0x10a and found[0][1]['code'] is None,'File source native contract differs')
        result.append(dict(method=found[0][0],class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',source_id='jdk:java.base',owner=owner,
            name=name,descriptor=desc,access=0x10a,operation=op))
    return result


def fields(c,layout,specs,S):
    candidate=layout['candidate'];S.check(candidate is not None and layout['diagnostic'] is None and layout['source_sha256']==c['origin']['sha256'],'File normal layout unavailable')
    result=[]
    for name,desc,access,width,reference in specs:
        declared=[(i,f) for i,f in enumerate(c['fields']) if (f['name'],f['descriptor'],f['access'])==(name,desc,access)]
        S.check(len(declared)==1,'File field source declaration differs: '+name)
        index=declared[0][0];member=dict(owner=c['id'],index=index,name=name,descriptor=desc,access=access)
        matches=[f for f in candidate['fields'] if f['member']==member];S.check(len(matches)==1,'File native field not in normal layout')
        f=matches[0];off=f['offset']
        S.check(f['storage_bytes']==width and f['reference']==reference and off%width==0 and off+width<=candidate['payload_bytes'] and
                (off<candidate['reference_prefix']*8)==reference,'File field bounds or reference-prefix identity differs')
        result.append(dict(name=name,descriptor=desc,offset=off,width=width))
    for i,a in enumerate(result):
        for b in result[i+1:]:S.check(a['offset']+a['width']<=b['offset'] or b['offset']+b['width']<=a['offset'],'File native fields overlap')
    return result


def index(summary,classes,S):
    names={(c['origin']['loader'],c['name']):c for c in classes}
    wanted={names['bootstrap',owner]['id'] for owner,_,_,_ in SPECS};layouts={}
    for line in S.checked(summary['layouts']).read_text(encoding='utf-8').splitlines():
        r=json.loads(line)
        if r['class_id'] in wanted:layouts[r['class_id']]=r
    streams=[]
    for owner in ('java/io/FileInputStream','java/io/FileOutputStream'):
        c=names['bootstrap',owner];f=fields(c,layouts[c['id']],[('fd','Ljava/io/FileDescriptor;',0x12,8,True)],S)[0]
        streams.append(dict(class_id=c['id'],source_sha256=c['origin']['sha256'],fd_offset=f['offset'],fd_width=8))
    c=names['bootstrap','java/io/FileDescriptor'];S.check(c['access']&0x611==0x11,'FileDescriptor must retain its original final class contract')
    descriptor=dict(class_id=c['id'],source_sha256=c['origin']['sha256'],fields=fields(c,layouts[c['id']],[('fd','I',2,4,False),('handle','J',2,8,False),('append','Z',2,1,False)],S))
    return dict(schema=1,streams=streams,descriptor=descriptor,source_transform_chain='original_locked_no_transforms',
        standard_handle_policy='Windows_GetStdHandle_0_1_2_other_minus_one',append_policy='Windows_false',byte_order_policy='native_DWORD_memory_probe',
        file_IO_natives_provided=False,game_started=False)


def data(meta):
    imports={f"boom_layout{s['class_id']}" for s in meta['streams']}|{f"boom_layout{meta['descriptor']['class_id']}"}
    parts=['.const\nALIGN 8\nPUBLIC boom_provider_file_bootstrap_pool\nboom_provider_file_bootstrap_pool DWORD 04F49464Eh,1\n QWORD OFFSET provider_file_input_pool,OFFSET provider_file_output_pool,OFFSET provider_file_descriptor_pool,0,0\n']
    for prefix,s in zip(('input','output'),meta['streams']):
        parts.append(f"ALIGN 8\nprovider_file_{prefix}_table DWORD 053465442h,1\n QWORD OFFSET boom_layout{s['class_id']}\n DWORD {s['fd_offset']},8\n QWORD 0\n.data\nALIGN 8\nprovider_file_{prefix}_pool DWORD 05346504Ch,1\n QWORD OFFSET provider_file_{prefix}_table,0,0\n.const\n")
    d=meta['descriptor'];parts.append(f"ALIGN 8\nprovider_file_descriptor_table DWORD 046445442h,1\n QWORD OFFSET boom_layout{d['class_id']}\n")
    parts.extend(f" DWORD {f['offset']},{f['width']}\n" for f in d['fields'])
    parts.append(' QWORD 0\n.data\nALIGN 8\nprovider_file_descriptor_pool DWORD 04644504Ch,1\n QWORD OFFSET provider_file_descriptor_table,0,0\n')
    return ''.join(parts),imports
