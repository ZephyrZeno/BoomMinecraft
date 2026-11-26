"""Copy real generated thunks into an explicitly VM-prepared BSM fixture.

This tests emitted argument frames/normal strings, not original bootstrap Java
initialization. The fixture initializer reports an unbound service if invoked.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def prepare(batch,output):
    batch,output=Path(batch),Path(output);output.mkdir(parents=True,exist_ok=True)
    s=json.loads((batch/'summary.json').read_text(encoding='utf-8'));c=s['string_concat']
    index=Path(c['index']['path']);assert hashlib.sha256(index.read_bytes()).hexdigest()==c['index']['digest']['sha256']
    with zipfile.ZipFile(index) as z:sites=list(map(json.loads,z.read('sites.jsonl').splitlines()))
    chosen={}
    for site in sites:
        p=site['plan']
        if p is not None and not p['conversions']:
            chosen.setdefault(site['descriptor'],site)
    selected=sorted(chosen.values(),key=lambda r:r['label'])[:128]
    assert len(selected)>=3
    sources=load('concat_fixture_sources','batch-source.py').Sources();model=load('concat_fixture_model','verify-batch-concat.py')
    parts=[];hashes={}
    for site in selected:
        label=site['label'];path=c['units'][site['assembly_unit']]['assembly']['path']
        data=model.body(label,site['plan'],c['bootstrap']['class_id'],c['source_layout']).partition('.code\n')[0]
        data=sources.fragment(path,label,data);function=sources.function(path,label);parts.extend((data,'.code\n'+function))
        hashes[label]=dict(function=hashlib.sha256(function.encode()).hexdigest(),data=hashlib.sha256(data.encode()).hexdigest())
    bsm=c['bootstrap']['class_id']
    fixture=f'.data?\nboom_concat_fixture_failure QWORD ?\n.data\nALIGN 8\nPUBLIC boom_class{bsm}\nPUBLIC boom_concat_fixture_class\nboom_concat_fixture_class LABEL BYTE\nboom_class{bsm} DWORD 0434C4153h,2,2,0\n QWORD OFFSET boom_concat_fixture_initialize\n DWORD {bsm},0\n QWORD 0,0,0,OFFSET boom_concat_fixture_failure\n.code\nboom_concat_fixture_initialize PROC\n mov DWORD PTR [rcx],20\n mov eax,20\n ret\nboom_concat_fixture_initialize ENDP\n'
    body=fixture+'\n'.join(parts)
    defined=set(re.findall(r'(?m)^\s*(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)',body))
    calls=set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_\w+)',body));refs=set(re.findall(r'\bboom_\w+\b',body))-defined
    prefix=['option casemap:none']+[f"EXTERN {n}:{'PROC' if n in calls else 'BYTE'}" for n in sorted(refs)]+[f"PUBLIC {r['label']}" for r in selected]
    (output/'fixture.asm').write_text('\n'.join(prefix)+'\n.code\n'+body+'\nEND\n',encoding='utf-8')
    cases=[];entries=[]
    for site in selected:
        p=site['plan']
        for variant in range(3):
            args=[]
            for i,t in enumerate(p['arguments']):
                kind={'B':1,'S':1,'I':1,'J':2,'Z':3,'C':4,'Ljava/lang/String;':5}[t]
                bits={'B':[-128,0,127],'S':[-32768,0,32767],'I':[-2147483648,0,2147483647],
                      'J':[-9223372036854775808,0,9223372036854775807],'Z':[0,1,0],'C':[0,0xd800,0x4e2d]}.get(t,[0,1,0])[variant]
                text=([ord('a'),0,0xd800,ord('z'),0xdc00] if variant==2 else [ord('q'),255] if variant==1 else None) if kind==5 else None
                args.append((kind,bits,text))
            rows=[(0,0,r['utf16']) if r['kind']=='literal' else (r['operation'],r['index'],[]) for r in p['parts']]
            cases.append((args,rows));entries.append(site['label'])
    with (output/'cases.bin').open('wb') as f:
        def integer(i):f.write(struct.pack('<i',i))
        def text(t):
            integer(-1 if t is None else len(t))
            if t:f.write(struct.pack('<'+'H'*len(t),*t))
        integer(0x4a434f4e);integer(len(cases))
        for args,rows in cases:
            integer(len(args))
            for kind,bits,t in args:integer(kind);f.write(struct.pack('<Q',bits&0xffffffffffffffff));text(t)
            integer(len(rows))
            for kind,index,t in rows:integer(kind);integer(index);text(t)
    (output/'entries.txt').write_text('\n'.join(entries)+'\n',encoding='ascii')
    objects=[u['object']['path'] for u in s['string_literals']['units']]+[s['numeric_kernel_object']['path']]
    exports=[r['label'] for r in selected]+['boom_concat_fixture_class','boom_heap_ptr','boom_java_string_literal_pool','boom_java_string_literals_bind_heap']
    result=dict(batch=str(batch.resolve()),selected_sites=selected,source_hashes=hashes,objects=objects,exports=exports,
        fixture_class_descriptor=True,original_bootstrap_initialization_executed=False,original_Java_conversions_executed=False,
        source_batch_summary_sha256=hashlib.sha256((batch/'summary.json').read_bytes()).hexdigest(),game_started=False)
    (output/'fixture.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=prepare(a.batch,a.output);print('Copied real source concat thunks='+str(len(r['selected_sites'])))
