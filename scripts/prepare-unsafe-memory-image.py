"""Select source-verified raw-slot memory fixtures without changing startup ABI."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];output=a.output.resolve();assert output.is_relative_to((root/'.boom').resolve())
    source=json.loads(a.source.read_text());batch=Path(source['batch']);s=json.loads((batch/'summary.json').read_text())
    assert s['schema']>=21 and s['input_fingerprint']==source['source_input_fingerprint']
    with zipfile.ZipFile(s['unsafe_memory']['index']['path']) as z:methods=[json.loads(l) for l in z.read('methods.jsonl').splitlines()]
    expected=[f'bootstrap:java/util/concurrent/atomic/AtomicInteger:{name}:{desc}' for name,desc in
        [('<init>','(I)V'),('get','()I'),('compareAndSet','(II)Z'),('getAndIncrement','()I')]]
    expected += [f"bootstrap:jdk/internal/misc/Unsafe:{m['name']}:{m['descriptor']}" for m in methods]
    assert source['entries']==expected and len(methods)==42
    model=module('memory_fixture_globals','diagnostic-closure.py');coff=module('memory_fixture_coff','verify-batch-assembly.py')
    known,providers,identity=model.globals_index(batch,s,a.runtime,coff);selector=module('memory_fixture_source','prepare-class-init-probe.py')
    manifest=selector.prepare(batch,Path(source['plan']),output,[tuple(x.split(':',1)) for x in source['class_roots']],
        [tuple(x.split(':',3)) for x in expected],diagnostic=dict(admit_methods=[],known_symbols=known,data_providers=providers,global_identity=identity))
    manifest['exports'].append('boom_java_string_literal_root_count')
    manifest['diagnostic_selection_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['explicit_typed_memory_fixture_entries']=True
    (output/'closure.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(diagnostic_only=True,memory_fixture_entries=42,game_started=False)))
