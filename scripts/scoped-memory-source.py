"""Original ScopedMemoryAccess registration; foreign close remains unavailable."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('scoped_memory_original_methods',Path(__file__).with_name('verify-batch-frames.py'))
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
OWNER='jdk/internal/misc/ScopedMemoryAccess'
KERNELS=['classes32.asm','scoped_memory.asm']
SPECS=(('registerNatives','()V',0x10a),('closeScope0','(Ljdk/internal/foreign/MemorySessionImpl;)Z',0x100))


def index(summary,classes,S):
    owners=[c for c in classes if c['name']==OWNER and c['origin']['loader']=='bootstrap']
    S.check(len(owners)==1,'ScopedMemoryAccess owner missing or ambiguous')
    c=owners[0]
    S.check(c['origin']['source_id']=='jdk:java.base' and not c['origin'].get('generated') and c['access']==0x21,
            'ScopedMemoryAccess requires its original bootstrap class')
    owner,raw=R.original_methods(S.original_class(summary,c))
    S.check(owner==OWNER and len(raw)==len(c['method_ids']),'ScopedMemoryAccess original method inventory differs')
    natives=[(i,m) for i,m in zip(c['method_ids'],raw) if m['access']&0x100]
    S.check(len(natives)==2,'ScopedMemoryAccess original native inventory differs')
    declarations=[]
    for op,(name,desc,access) in enumerate(SPECS):
        found=[(i,m) for i,m in natives if (m['name'],m['descriptor'])==(name,desc)]
        S.check(len(found)==1 and found[0][1]['access']==access and found[0][1]['code'] is None,
                'ScopedMemoryAccess original native declaration differs: '+name)
        declarations.append(dict(method=found[0][0],class_id=c['id'],class_sha256=c['origin']['sha256'],loader='bootstrap',
            source_id='jdk:java.base',owner=OWNER,name=name,descriptor=desc,access=access,operation=op))
    return dict(schema=1,registration=declarations[0],unavailable_close=declarations[1],registered_entries=1,
        close_target='boom_scoped_close_unavailable',target_address_policy='canonical_runtime_export_from_IAT',close_scope_implemented=False,thread_handshake_implemented=False,
        source_transform_chain='original_locked_no_transforms',game_started=False)


def data():
    return '.data\nALIGN 8\nPUBLIC boom_provider_scoped_memory_pool\nboom_provider_scoped_memory_pool DWORD 0504E4353h,1,0,1\n QWORD 0,0\n'
