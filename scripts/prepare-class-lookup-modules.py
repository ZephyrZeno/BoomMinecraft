"""Explicit source-layout bootstrap Module inputs for development lookup tests."""
import argparse
import hashlib
import json
from pathlib import Path
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args();source=json.loads(a.source.read_text(encoding='utf-8'))
    s=json.loads((Path(source['batch'])/'summary.json').read_text(encoding='utf-8'));assert s['input_fingerprint']==source['source_input_fingerprint']
    artifact=s['layouts'];path=Path(artifact['path'])
    with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==artifact['digest']['sha256']
    shape=s['class_literals']['source_shape'];module=shape['module_type']
    with path.open(encoding='utf-8') as stream:layout=next(r for line in stream if (r:=json.loads(line))['class_id']==module)
    fields=layout['candidate']['fields'];name=next(f for f in fields if f['member']['owner']==module and f['member']['name']=='name' and f['member']['descriptor']=='Ljava/lang/String;')
    loader=next(f for f in fields if f['member']['owner']==module and f['member']['name']=='loader')
    assert name['reference'] and name['storage_bytes']==8 and loader['offset']==shape['module_loader_offset']
    modules=[m for m in s['class_literals']['modules'] if m['loader']==0]
    data=''.join(f"{m['id']}\t{module}\t{name['offset']}\t{m['name']}\n" for m in modules)
    (a.source.parent/'bootstrap-modules.tsv').write_text(data,encoding='utf-8');print(json.dumps(dict(fixture_modules=len(modules),Module_constructor_executed=False,module_bootstrap_executed=False)))
