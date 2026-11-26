"""Prove copied source thunks/data, and explicitly label the fixture class."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def verify(root):
    root=Path(root);manifest=json.loads((root/'fixture.json').read_text(encoding='utf-8'));batch=Path(manifest['batch'])
    s=json.loads((batch/'summary.json').read_text(encoding='utf-8'));c=s['string_concat'];coff=load('concat_fixture_coff','verify-batch-assembly.py')
    assert hashlib.sha256((batch/'summary.json').read_bytes()).hexdigest()==manifest['source_batch_summary_sha256']
    with zipfile.ZipFile(coff.artifact(batch,c['index'],'string-concat')) as z:original={r['label']:r for r in map(json.loads,z.read('sites.jsonl').splitlines())}
    sources=load('concat_fixture_text','batch-source.py').Sources();model=load('concat_fixture_plan','verify-batch-concat.py')
    asm=(root/'fixture.asm').read_text(encoding='utf-8')
    for row in manifest['selected_sites']:
        label=row['label'];assert original[label]==row and not row['plan']['conversions']
        path=c['units'][row['assembly_unit']]['assembly']['path'];data=model.body(label,row['plan'],c['bootstrap']['class_id'],c['source_layout']).partition('.code\n')[0]
        data=sources.fragment(path,label,data);function=sources.function(path,label)
        assert asm.count(data)==1 and asm.count('.code\n'+function)==1
        assert manifest['source_hashes'][label]==dict(function=hashlib.sha256(function.encode()).hexdigest(),data=hashlib.sha256(data.encode()).hexdigest())
    defined,undefined=coff.coff_symbols(root/'fixture.obj')
    assert defined=={r['label'] for r in manifest['selected_sites']}|{f"boom_class{c['bootstrap']['class_id']}",'boom_concat_fixture_class','boom_concat_fixture_initialize'}
    assert undefined=={'boom_heap_ptr',f"boom_layout{c['source_layout']['class_id']}",'boom_class_ensure32','boom_java_concat'}
    assert manifest['fixture_class_descriptor'] and not manifest['original_bootstrap_initialization_executed'] and not manifest['original_Java_conversions_executed']
    return dict(verified=True,source_thunks=len(manifest['selected_sites']),scope='copied_source_thunks_data_COFF_with_fixture_class_descriptor',
                original_bootstrap_initialization_executed=False,game_started=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);a=p.parse_args();r=verify(a.root)
    (a.root/'fixture-verification.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r))
