"""Select the explicit raw-slot source fixture; startup entry ABI stays strict."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
def module(name,file):
    s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--profile',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];assert a.output.resolve().is_relative_to((root/'.boom').resolve());source=json.loads(a.source.read_text());batch=Path(source['batch']);s=json.loads((batch/'summary.json').read_text())
    assert s['schema']>=22 and s['input_fingerprint']==source['source_input_fingerprint']
    expected=['bootstrap:java/lang/Class:forName0:(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;',
              'bootstrap:java/lang/ClassLoader:findBootstrapClass:(Ljava/lang/String;)Ljava/lang/Class;',
              'bootstrap:java/lang/Class:forName:(Ljava/lang/String;ZLjava/lang/ClassLoader;)Ljava/lang/Class;',
              'bootstrap:java/lang/Enum:name:()Ljava/lang/String;','bootstrap:java/lang/Enum:ordinal:()I']
    assert source['entries']==expected
    profile=dict(admitted_methods=[],admitted_classes=[])
    if a.profile:
        profile=json.loads(a.profile.read_text());assert profile['diagnostic_only'] and profile['native_implementations_added']==0
        assert profile['source_class_id'] in [r['class_id'] for r in source['enums']]
    model=module('lookup_fixture_globals','diagnostic-closure.py');coff=module('lookup_fixture_coff','verify-batch-assembly.py');selector=module('lookup_fixture_source','prepare-class-init-probe.py')
    known,providers,identity=model.globals_index(batch,s,a.runtime,coff)
    m=selector.prepare(batch,Path(source['plan']),a.output,[('bootstrap','java/lang/Class')],[tuple(e.split(':',3)) for e in expected],
        diagnostic=dict(admit_methods=profile['admitted_methods'],admit_classes=profile.get('admitted_classes',[]),known_symbols=known,data_providers=providers,global_identity=identity))
    m['explicit_raw_slot_class_lookup_fixture']=True;m['diagnostic_selection_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (a.output/'closure.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(dict(diagnostic_only=True,game_started=False)))
