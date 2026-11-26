"""Select original intern/getName entries and source-bound static test cases."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import zipfile


def prepare_cases(batch,output):
    batch,output=Path(batch),Path(output);output.mkdir(parents=True,exist_ok=True)
    summary=json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(summary['string_literals']['index']['path']) as z:
        literals=list(map(json.loads,z.read('canonical.jsonl').splitlines()))
    with zipfile.ZipFile(summary['class_literals']['index']['path']) as z:
        types=list(map(json.loads,z.read('types.jsonl').splitlines()))
        names={r['type_id']:r['canonical'] for r in map(json.loads,z.read('names.jsonl').splitlines())}
        canonical=list(map(json.loads,z.read('canonical_names.jsonl').splitlines()))
    indices=sorted(set([0,len(literals)-1]+[i*len(literals)//128 for i in range(128)]))
    cases=[(0,i,-1,literals[i]['utf16']) for i in indices]
    candidates=[t for t in types if t['flags']&1 and t['component'] is None and canonical[names[t['type_id']]]['literal'] is None]
    cases.extend((1,names[t['type_id']],t['type_id'],canonical[names[t['type_id']]]['utf16']) for t in candidates[:10])
    with (output/'static-cases.bin').open('wb') as f:
        f.write(struct.pack('<II',0x4a494e54,len(cases)))
        for kind,index,type_id,units in cases:
            f.write(struct.pack('<iiii',kind,index,type_id,len(units)))
            f.write(struct.pack('<'+'H'*len(units),*units))
    prefix='BoomNativeIntern_96_7fd34e_'
    dynamic=[list(map(ord,prefix+f'{i:08x}')) for i in range(8192)]
    dynamic.extend((list(map(ord,prefix+'Aa')),list(map(ord,prefix+'BB')),[ord('Z'),0,255,0x4e2d,0xd800,ord('q'),0xdc00,0xd83d,0xde00],[ord('x')]*70001))
    with (output/'dynamic-cases.bin').open('wb') as f:
        f.write(struct.pack('<II',0x4a494e44,len(dynamic)))
        for units in dynamic:
            f.write(struct.pack('<I',len(units)));f.write(struct.pack('<'+'H'*len(units),*units))
    return summary


def prepare(batch,plan,output):
    summary=prepare_cases(batch,output)
    if summary['schema']<12:raise ValueError('Production intern probe needs schema 12')
    spec=importlib.util.spec_from_file_location('intern_source_selector',Path(__file__).with_name('prepare-class-init-probe.py'));selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)
    roots=[('bootstrap','java/lang/String','intern','()Ljava/lang/String;'),('bootstrap','java/lang/Class','getName','()Ljava/lang/String;')]
    result=selector.prepare(batch,plan,output,[],roots)
    result['intern_entries']={m['name']:m['symbol'] for m in result['requested_method_roots']}
    (Path(output)/'closure.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=prepare(a.batch,a.plan,a.output);print(json.dumps(dict(Java_methods=len(r['selected_methods']),native_methods=len(r['selected_String_intern_natives']))))
