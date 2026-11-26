"""Select two unmodified, emitted Java method bodies and actual literal exports."""
import argparse
import json
from pathlib import Path
import re
import random
import zipfile


def prepare(batch, output):
    batch, output = Path(batch), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summary = json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    literal = summary['string_literals']
    with zipfile.ZipFile(literal['index']['path']) as bundle:
        canonical = [json.loads(line) for line in bundle.read('canonical.jsonl').splitlines()]
        aliases = [json.loads(line) for line in bundle.read('bindings.jsonl').splitlines()]
    with (output/'input-utf16.txt').open('w', encoding='ascii', newline='\n') as stream:
        for row in canonical: stream.write(''.join(f'{u:04x}' for u in row['utf16'])+'\n')
    # Include aliases with the same contents from different source constant pools.
    picks, seen = {}, {}
    for row in aliases:
        if len(picks) < 32: picks[row['symbol']] = row['canonical']
        if row['canonical'] in seen and len(picks) < 96:
            first = seen[row['canonical']]; picks[first['symbol']] = first['canonical']
            picks[row['symbol']] = row['canonical']
        seen[row['canonical']] = row
    (output/'aliases.tsv').write_text(''.join(f'{name}\t{id_}\n' for name,id_ in picks.items()),encoding='ascii')
    methods, bodies, boxed, cache = {}, [], {}, {}
    requests={'String':[('value','()[B'),('isEmpty','()Z')]}
    if summary['schema']>=4:
        requests.update({name:[('<init>',f'({desc})V'),(getter,f'(){desc}')] for name,desc,getter in
                         [('Boolean','Z','booleanValue'),('Byte','B','byteValue'),('Character','C','charValue'),
                          ('Short','S','shortValue'),('Integer','I','intValue'),('Long','J','longValue'),
                          ('Float','F','floatValue'),('Double','D','doubleValue')]})
        requests['Number']=[('<init>','()V')]
        requests['Object']=[('<init>','()V')]
        with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as bundle:
            wanted={r['id']:r['name'].split('/')[-1] for r in map(json.loads,bundle.read('types.jsonl').splitlines())
                    if r['defining_loader']=='bootstrap' and r['name'].startswith('java/lang/') and r['name'].split('/')[-1] in requests}
    else: wanted={literal['source_layout']['class_id']:'String'}
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as bundle:
            entries=set(bundle.namelist())
            for class_id,short in list(wanted.items()):
                path=f'classes/{class_id:06}.json'
                if path not in entries: continue
                unit=json.loads(bundle.read(path));selected={}
                for name,descriptor in requests[short]:
                    method,=[m for m in unit['methods'] if (m['name'],m['descriptor'])==(name,descriptor)]
                    assert method['assembly_emitted'] and method['operand_verified']
                    assembly_path=shard['units'][method['assembly_unit']]['assembly']['path']
                    if assembly_path not in cache: cache[assembly_path]=Path(assembly_path).read_text(encoding='utf-8')
                    assembly=cache[assembly_path];symbol=f"boom_m{method['id']}"
                    symbols=[symbol+'_body'] if short=='String' else [symbol,symbol+'_body']
                    for exported in symbols:
                        match=re.search(rf'(?m)^{exported} PROC\b[\s\S]*?^{exported} ENDP\n',assembly)
                        assert match,exported
                        bodies.append(match[0])
                    record=dict(symbol=symbol+'_body' if short=='String' else symbol,code_sha256=method['code_sha256'],class_sha256=unit['source_sha256'])
                    selected[name]=record
                    if short=='String':methods[name]=record
                if short not in ('String','Number','Object'):boxed[short]=dict(class_id=class_id,constructor=selected['<init>'],getter=selected[requests[short][1][0]])
                wanted.pop(class_id)
        if not wanted:break
    assert len(methods)==2 and not wanted
    body = '\n'.join(bodies)
    definitions = set(re.findall(r'(?m)^\s*(boom_[A-Za-z0-9_]+)(?::|\s+PROC\b)',body))
    calls = set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_[A-Za-z0-9_]+)',body))
    references = set(re.findall(r'\bboom_[A-Za-z0-9_]+\b',body))-definitions
    prefix = ['option casemap:none']
    for symbol in sorted(references): prefix.append(f"EXTERN {symbol}:{'PROC' if symbol in calls else 'BYTE'}")
    for symbol in sorted(set(re.findall(r'(?m)^(boom_\w+) PROC\b',body))): prefix.append(f'PUBLIC {symbol}')
    (output/'original-string-methods.asm').write_text('\n'.join(prefix)+'\n.code\n'+body+'\nEND\n',encoding='utf-8')
    objects=[u['object']['path'] for u in literal['units']]
    if summary['schema']>=4: objects.extend(u['object']['path'] for u in summary['runtime_metadata']['units'])
    result = dict(batch=str(batch.resolve()),canonical_strings=len(canonical),aliases=len(picks),methods=methods,
                  objects=objects,source_layout=literal['source_layout'])
    if boxed:
        result['boxed_types']=boxed
        (output/'boxed-types.tsv').write_text(''.join(f"{name}\t{r['class_id']}\t{r['constructor']['symbol']}\t{r['getter']['symbol']}\n" for name,r in boxed.items()),encoding='ascii')
        rng=random.Random(0x4d455441);cases=[]
        for name in boxed:
            width={'Boolean':1,'Byte':8,'Short':16,'Character':16,'Integer':32,'Long':64,'Float':32,'Double':64}[name]
            values=set(range(1<<width)) if width<=8 else {0,1,(1<<width)-1,1<<(width-1),(1<<(width-1))-1}
            if width>8:values.update(rng.getrandbits(width) for _ in range(256))
            if name in ('Float','Double'):
                exponent=0x7f800000 if name=='Float' else 0x7ff0000000000000
                values={v for v in values if v&exponent!=exponent}
                values.update((exponent,exponent|(1<<(width-1)),0x7fc00000 if name=='Float' else 0x7ff8000000000000))
            cases.extend(f'{name}\t{value:x}\n' for value in sorted(values))
        (output/'boxed-cases.tsv').write_text(''.join(cases),encoding='ascii')
    if summary['schema']>=4:
        metadata=summary['runtime_metadata']
        with zipfile.ZipFile(metadata['index']['path']) as bundle:
            rows=[json.loads(line) for line in bundle.read('runtime.jsonl').splitlines()]
            fields=[json.loads(line) for line in bundle.read('fields.jsonl').splitlines()]
        (output/'runtime-objects.tsv').write_text(''.join(f"{r['type_id']}\t{r['kind']}\t{r['payload_bytes']}\t{r['reference_prefix']}\t{r['shift']}\n" for r in rows),encoding='ascii')
        with (output/'runtime-fields.tsv').open('w',encoding='ascii',newline='\n') as stream:
            for field in fields:
                for row in field['rows']:
                    stream.write(f"{field['id']}\t{row['receiver_class']}\t{row['offset']}\t{field['storage_bytes']}\n")
        picks=fields[:48]+fields[-48:]
        (output/'runtime-thunks.tsv').write_text(''.join(f"{f['id']}\t{f['rows'][0]['receiver_class']}\t{f['rows'][0]['offset']}\n" for f in picks),encoding='ascii')
        result['runtime_metadata']=dict(type_capacity=metadata['type_capacity'],field_capacity=metadata['field_capacity'],
            rows=len(rows),field_maps=len(fields),receiver_offsets=metadata['receiver_offsets'],thunk_ids=[f['id'] for f in picks])
    (output/'probe.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.batch,args.output),indent=2))
