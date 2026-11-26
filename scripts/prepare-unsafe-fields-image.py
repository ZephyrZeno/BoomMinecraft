"""Select the two explicit original AtomicInteger fixture entries, not startup entries.

The startup runner retains its ()V / explicit predicate contract. This image is
called only by the separate raw-slot field development host and checked by the
same independent original-source/COFF/fail-stop verifiers.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];output=a.output.resolve()
    if not output.is_relative_to((root/'.boom').resolve()):raise ValueError('Fixture must stay within project .boom')
    source=json.loads(a.source.read_text());batch=Path(source['batch']);summary=json.loads((batch/'summary.json').read_text())
    if summary['input_fingerprint']!=source['source_input_fingerprint']:raise ValueError('Fixture/source input identity differs')
    expected=[]
    for owner,arg in [('java/util/concurrent/atomic/AtomicInteger','I')]:
        expected.extend((f'bootstrap:{owner}:<init>:({arg})V',f'bootstrap:{owner}:get:(){arg}'))
    if source['entries']!=expected:raise ValueError('Only the two reviewed original fixture signatures are supported')
    model=module('field_fixture_globals','diagnostic-closure.py');coff=module('field_fixture_coff','verify-batch-assembly.py')
    known,providers,identity=model.globals_index(batch,summary,a.runtime,coff)
    selector=module('field_fixture_source','prepare-class-init-probe.py')
    manifest=selector.prepare(batch,Path(source['plan']),output,
        [tuple(s.split(':',1)) for s in source['class_roots']],[tuple(s.split(':',3)) for s in expected],
        diagnostic=dict(admit_methods=[],known_symbols=known,data_providers=providers,global_identity=identity))
    manifest['diagnostic_selection_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['explicit_atomic_field_fixture_entries']=True
    (output/'closure.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(diagnostic_only=True,fixture_entries=2,game_started=False)))
