"""A thrown Java oop reaching a class initializer without an EXVM must fail closed and remain rooted as its cause."""
import argparse
import ctypes as c
import hashlib
import json
import os
import zipfile
from pathlib import Path
from test_wait import P,Q,U,Context,bind,require


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-state',type=Path,help='Checked diagnostic source image for a ready-EXVM Error-subclass control')
    args=parser.parse_args()
    folder=args.runtime.resolve()
    root=Path(__file__).resolve().parents[2]
    manifest=json.loads((folder/'runtime.json').read_bytes())
    for name in ('unwind.asm','classes32.asm'):
        require(hashlib.sha256((root/'native/runtime'/name).read_bytes()).hexdigest()==manifest['sources']['native/runtime/'+name],
                'current source '+name)
    dll=folder/'boom-runtime.dll'
    require(hashlib.sha256(dll.read_bytes()).hexdigest()==manifest['sha256'],'runtime PE')
    rt=c.CDLL(str(dll))
    heap=bind(rt,'heap_create',P,Q)(1<<20)
    object_=bind(rt,'heap_alloc',P,P,Q,U,Q)(heap,8,0,19)
    require(object_,'heap oop for retained cause')
    initial=bind(rt,'exception_init_failure',P,P)
    ensure=bind(rt,'class_ensure32',U,P,P)
    require(not initial(None),'null caller')
    callback_type=c.CFUNCTYPE(None,P,P)
    @callback_type
    def throw_fixture(ctx,unused):
        U.from_address(ctx).value=16
        U.from_address(ctx+4).value=42
        U.from_address(ctx+8).value=703
        P.from_address(ctx+16).value=object_
    records=[]
    configurations=[('absent',None,20),('foreign ABI',(Q*20)(0x11111222),7),
                    ('not ready',(Q*20)(0x14558564d,1),20),('invalid type map',(Q*20)(0x14558564d,2),7)]
    for name,plan,kind in configurations:
        plan_address=c.addressof(plan) if plan is not None else 0
        ctx=Context(0,0,0,plan_address)
        cause=P()
        cls=(Q*8)(0x2434c4153,0,c.cast(throw_fixture,P).value,0,0,0,0,c.addressof(cause))
        require(ensure(cls,ctx)==1 and ctx[0]==((42<<32)|kind) and ctx[1]==703 and ctx[2]==0 and ctx[3]==plan_address,
                'explicit original-site failure '+name)
        require(cause.value==object_ and cls[1]==3 and cls[4]==ctx[0] and cls[5]==ctx[1],
                'failed class retains its original cause '+name)
        second=Context()
        require(ensure(cls,second)==1 and second[0]==9 and cause.value==object_,'subsequent failed class use '+name)
        records.append(dict(plan=name,source_failure_kind=kind,source_pc=42,original_cause_retained=True))
    if args.source_state:
        state=json.loads(args.source_state.read_bytes())
        batch=json.loads((Path(state['batch'])/'summary.json').read_bytes())
        source=Path(state['diagnostic'])/'round-000'
        verified=json.loads((source/'selection-verification.json').read_bytes())
        require(verified['verified'] and hashlib.sha256((source/'closure.json').read_bytes()).hexdigest()==
                verified['closure_manifest_sha256'],'valid source image metadata')
        with zipfile.ZipFile(batch['runtime_metadata']['index']['path']) as archive:
            wanted={r['name']:r['id'] for line in archive.open('types.jsonl') if (r:=json.loads(line))['name'] in
                    ('java/lang/Error','java/lang/AssertionError') and r['defining_loader']=='bootstrap'}
        require(len(wanted)==2,'source Error and subclass')
        with os.add_dll_directory(str(folder)):
            image=c.CDLL(str(source/'diagnostic-image.dll'))
        tmap=c.addressof(c.c_ubyte.in_dll(image,'boom_runtime_type_map'))
        table=P.from_address(tmap+16).value
        rows={U.from_address(p+16).value:p for i in range(U.from_address(tmap+8).value) if
              U.from_address((p:=table+40*i)+20).value==0 and U.from_address(p+16).value in set(wanted.values())}
        tag=P.from_address(rows[wanted['java/lang/AssertionError']]).value
        object_=bind(rt,'object_new',P,P,P,P)(heap,tag,Context())
        require(object_ and P.from_address(object_-8).value==tag,'real source AssertionError')
        vm=(Q*20)(0x14558564d,2)
        vm[4]=tmap
        vm[6]=P.from_address(rows[wanted['java/lang/Error']]+8).value
        ctx=Context(0,0,0,c.addressof(vm))
        cause=P()
        cls=(Q*8)(0x2434c4153,0,c.cast(throw_fixture,P).value,0,0,0,0,c.addressof(cause))
        require(ensure(cls,ctx)==1 and U.from_buffer(ctx).value==16 and ctx[2]==object_ and cause.value==object_,
                'an actual Error subtype propagates unchanged with ready type metadata')
        records.append(dict(plan='ready',source_failure_kind=16,original_cause_retained=True,source_type='java/lang/AssertionError'))
    require(bind(rt,'heap_destroy',U,P)(heap)==1,'heap teardown')
    result=dict(passed=True,runtime_sha256=manifest['sha256'],cases=records)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
