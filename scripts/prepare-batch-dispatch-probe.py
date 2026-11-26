"""Select exact bulk tables/stubs and original Buffer getter method envelopes.

Allocating source-shaped probe receivers does not execute Java constructors or
prove class initialization. Selected MASM is copied byte for byte; no fallback.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile


def prepare(batch, plan, output, automatic=False):
    batch, plan, output = Path(batch), Path(plan), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summary = json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    verified = json.loads((batch/'verification.json').read_text(encoding='utf-8'))
    assert summary['schema'] >= 6 and verified['dispatch']['verified']
    classes = list(map(json.loads, (plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    buffer, = [c for c in classes if c['name']=='java/nio/ByteBuffer' and c['origin']['loader']=='bootstrap']
    root, = [c for c in classes if c['name']=='java/lang/Object' and c['origin']['loader']=='bootstrap']
    source_methods={};requested={}
    for line in (plan/'methods.jsonl').open(encoding='utf-8'):
        m=json.loads(line);s=m['symbol']
        if m['class_id']==buffer['id'] and (s['name'],s['descriptor'])==('isDirect','()Z'):
            requested[s['name']]=m['id']
        if m['class_id']==root['id'] and (s['name'],s['descriptor'])==('equals','(Ljava/lang/Object;)Z'):
            equals=m['id']
    with zipfile.ZipFile(summary['dispatch']['index']['path']) as bundle:
        tables=[t for line in bundle.open('tables.jsonl') if (t:=json.loads(line))['resolved_method'] in requested.values()]
        table_ids={t['id'] for t in tables};sites={}
        for line in bundle.open('sites.jsonl'):
            s=json.loads(line)
            if s['table'] in table_ids and s['dispatch']['symbolic_owner']==buffer['id'] and s['dispatch']['receiver_constraint']==buffer['id']:
                sites.setdefault(s['table'],s)
    assert len(tables)==1 and len(sites)==1, 'Missing original ByteBuffer.isDirect dispatch contract'
    if automatic:
        spec=importlib.util.spec_from_file_location('automatic_dispatch_closure',Path(__file__).with_name('prepare-class-init-probe.py'))
        selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
        closure=selector.prepare(batch,plan,output,[],[('bootstrap','java/lang/Object','equals','(Ljava/lang/Object;)Z')],contract_roots=[s['label'] for s in sites.values()])
        closure['exports'].append('boom_batch_virtual_invoke')
        with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as bundle:
            types=[t for line in bundle.open('types.jsonl') if (t:=json.loads(line))['kind']==1 and (t['id']==buffer['id'] or buffer['id'] in t['ancestors'])]
        (output/'types.tsv').write_text(''.join(f"{t['name']}\t{t['id']}\n" for t in types),encoding='utf-8')
        closure.update(getters={'isDirect':next(iter(closure['selected_dispatch_sites']))},buffer_class=buffer['id'],object_class=root['id'],object_equals=f'boom_m{equals}',
                       selected_method_origins=closure['selected_methods'],selected_table_count=len(closure['selected_dispatch_tables']),
                       selected_receiver_rows=sum(len(t['rows']) for t in closure['selected_dispatch_tables'].values()),automatic_dependency_selection=True)
        (output/'closure.json').write_text(json.dumps(closure,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(automatic_dependency_selection=True,source_methods=len(closure['selected_methods']),tables=len(closure['selected_dispatch_tables']))))
        return
    wanted={r['target'] for t in tables for r in t['rows'] if r['target'] is not None}|{equals}
    assert all(t['array_target'] is None for t in tables)
    for line in (plan/'methods.jsonl').open(encoding='utf-8'):
        m=json.loads(line)
        if m['id'] in wanted:source_methods[m['id']]=m
    cache={}
    def text(path):
        if path not in cache:cache[path]=Path(path).read_text(encoding='utf-8')
        return cache[path]
    pieces=[];hashes={};origins={}
    def add(symbol, body, unit):
        assert body in text(unit['assembly']['path']), 'Selected MASM differs from bulk source: '+symbol
        hashes[symbol]=hashlib.sha256(body.encode()).hexdigest();pieces.append(body)
    def function(symbol, unit):
        match=re.search(rf'(?m)^{symbol} PROC\b[\s\S]*?^{symbol} ENDP\n',text(unit['assembly']['path']))
        assert match, symbol
        add(symbol,match[0],unit)
    function('boom_batch_virtual_invoke',summary['dispatch']['units'][0])
    for t in tables:
        assert t['diagnostic'] is None
        id_=t['id'];unit=summary['dispatch']['units'][t['assembly_unit']]
        expected=f".const\nALIGN 8\nPUBLIC boom_batch_vtable{id_}\nboom_batch_vtable{id_} DWORD 056445350h,1,{len(t['rows'])},0\n QWORD OFFSET boom_batch_vrows{id_},0\n DWORD 13,0\nboom_batch_vrows{id_} LABEL BYTE\n"
        for row in t['rows']:
            ptr=f"OFFSET boom_m{row['target']}" if row['target'] is not None else '0'
            expected+=f" DWORD {row['receiver']},{row['error']}\n QWORD {ptr}\n"
        add(f'boom_batch_vtable{id_}',expected,unit)
        s=sites[id_];symbol=s['label'];unit=summary['dispatch']['units'][s['assembly_unit']]
        expected=f".const\nALIGN 8\nboom_batch_vconstraints_{symbol} QWORD OFFSET boom_t{buffer['id']},OFFSET boom_t{buffer['id']}\n"
        add('constraints_'+symbol,expected,unit);pieces.append('.code\n');function(symbol,unit)
    owners={source_methods[id_]['class_id'] for id_ in wanted}
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as bundle:
            for cid in list(owners):
                entry=f'classes/{cid:06}.json'
                if entry not in bundle.namelist():continue
                c=json.loads(bundle.read(entry));assert c['source_sha256']==classes[cid]['origin']['sha256']
                for m in c['methods']:
                    if m['id'] not in wanted:continue
                    assert m['assembly_emitted'] and m['code_sha256']==source_methods[m['id']]['code_sha256']
                    unit=shard['units'][m['assembly_unit']]
                    pieces.append('.code\n');function(f"boom_m{m['id']}",unit);function(f"boom_m{m['id']}_body",unit)
                    origins[m['id']]=dict(class_sha256=c['source_sha256'],code_sha256=m['code_sha256'],class_id=cid)
                owners.remove(cid)
    assert not owners and set(origins)==wanted
    body='\n'.join(pieces)
    definitions=set(re.findall(r'(?m)^\s*(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)',body))
    procedures=set(re.findall(r'(?m)^(boom_\w+) PROC',body))
    calls=set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_\w+)',body))
    refs=set(re.findall(r'\bboom_\w+\b',body))-definitions
    assert not any(re.fullmatch(r'boom_m\d+(?:_body)?',s) for s in refs), 'Selected getters have additional Java dependencies'
    prefix=['option casemap:none']
    for symbol in sorted(refs):prefix.append(f"EXTERN {symbol}:{'PROC' if symbol in calls else 'BYTE'}")
    for symbol in sorted(procedures):prefix.append('PUBLIC '+symbol)
    (output/'dispatch-closure.asm').write_text('\n'.join(prefix)+'\n.code\n'+body+'\nEND\n',encoding='utf-8')
    with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as bundle:
        types=[t for line in bundle.open('types.jsonl') if (t:=json.loads(line))['kind']==1
               and (t['id']==buffer['id'] or buffer['id'] in t['ancestors'])]
    (output/'types.tsv').write_text(''.join(f"{t['name']}\t{t['id']}\n" for t in types),encoding='utf-8')
    getters={name:sites[next(t['id'] for t in tables if t['resolved_method']==id_)]['label'] for name,id_ in requested.items()}
    exports=sorted(procedures|{'boom_runtime_type_map','boom_batch_type_descriptors','boom_batch_runtime_rows','boom_java_string_literals_bind_heap','boom_java_string_literal_pool'})
    result=dict(batch=str(batch.resolve()),getters=getters,buffer_class=buffer['id'],object_class=root['id'],object_equals=f'boom_m{equals}',
                selected_method_origins=origins,selected_source_sha256=hashes,
                selected_table_count=len(tables),selected_receiver_rows=sum(len(t['rows']) for t in tables),
                exports=exports,objects=[u['object']['path'] for module in ('string_literals','runtime_metadata') for u in summary[module]['units']]+[summary['numeric_kernel_object']['path']],
                class_initialization_executed=False,constructors_executed=False,game_started=False)
    (output/'closure.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(selected_methods=len(wanted),tables=len(tables),getters=getters)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--automatic-closure',action='store_true')
    args=parser.parse_args();prepare(args.batch,args.plan,args.output,args.automatic_closure)
