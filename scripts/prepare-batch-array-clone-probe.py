"""Link every source-generated array clone adapter with real source metadata."""
import argparse
import json
from pathlib import Path
import zipfile

def prepare(batch,output):
    batch,output=Path(batch),Path(output);output.mkdir(parents=True,exist_ok=True)
    summary=json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    verification=json.loads((batch/'verification.json').read_text(encoding='utf-8'))
    assert summary['schema']>=7 and verification['array_clone']['verified']
    with zipfile.ZipFile(summary['array_clone']['index']['path']) as bundle:
        sites=list(map(json.loads,bundle.read('sites.jsonl').splitlines()))
    arrays={a['id']:a for a in map(json.loads,Path(summary['array_types']['path']).read_text(encoding='utf-8').splitlines())}
    (output/'clones.tsv').write_text(''.join(f"{s['label']}\t{s['array_type']}\t{arrays[s['array_type']]['descriptor']}\n" for s in sites),encoding='utf-8')
    exports=[s['label'] for s in sites]+['boom_batch_array_clone_pool','boom_runtime_type_map','boom_batch_type_descriptors',
        'boom_java_string_literals_bind_heap','boom_java_string_literal','boom_java_string_literal_pool']
    result=dict(batch=str(batch.resolve()),sites=len(sites),source_array_types=summary['array_clone']['source_array_types'],
        object_class=summary['array_clone']['contract']['object_class'],exports=exports,
        objects=[u['object']['path'] for key in ('array_clone','string_literals','runtime_metadata') for u in summary[key]['units']],
        array_clone_assembly_sources=[u['assembly'] for u in summary['array_clone']['units']],
        Java_constructors_executed=False,game_started=False)
    (output/'closure.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(sites=len(sites),array_types=result['source_array_types'])))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.batch,args.output)
