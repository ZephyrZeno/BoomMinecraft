"""Select the original Raw constructor/getter and prepare normal-object cases."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zipfile


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def prepare(batch, plan, ir, output, fixture=False):
    batch, plan, ir, output = map(Path, (batch, plan, ir, output))
    output.mkdir(parents=True, exist_ok=True)
    summary = json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    source = json.loads((ir/'summary.json').read_text(encoding='utf-8'))
    if summary['ir_identity'] != source['identity'] or summary['input_fingerprint'] != source['input_fingerprint']:
        raise ValueError('Property probe source input identity differs')
    classes = list(map(json.loads, (plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    c = next(c for c in classes if (c['origin']['loader'], c['name']) == ('bootstrap', 'jdk/internal/util/SystemProps$Raw'))
    raw = None
    with (ir/'shards.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            shard = json.loads(line)
            entry = next((e for e in shard['entries'] if e['class_id'] == c['id']), None)
            if entry:
                with zipfile.ZipFile(shard['zip']['path']) as z: payload = z.read(entry['path'])
                if hashlib.sha256(payload).hexdigest() != entry['digest']['sha256']:
                    raise ValueError('Raw IR payload changed')
                raw = json.loads(payload); break
    if raw is None or raw['origin'] != c['origin']:
        raise ValueError('Raw source origin differs')
    field = None
    with Path(summary['layouts']['path']).open(encoding='utf-8') as stream:
        for line in stream:
            layout = json.loads(line)
            if layout['class_id'] == c['id']:
                field = next(f for f in layout['candidate']['fields'] if f['member']['name'] == 'platformProps')
                break
    with zipfile.ZipFile(summary['runtime_metadata']['index']['path']) as z:
        array = next(t for t in map(json.loads, z.read('types.jsonl').splitlines()) if
                     (t['defining_loader'], t['name']) == ('bootstrap', '[Ljava/lang/String;'))
    verifier = module('property_case_model', 'verify-batch-properties.py')
    if fixture:
        indices = {f['name']: raw['constants'][str(f['constant_value'])]['Int'] for f in raw['fields'] if f['name'].endswith('_NDX')}
        profile = dict(schema=1, java_home=str(output.resolve()), class_path='development-source-layout-fixture',
                       library_path=str(output.resolve()), properties=[])
        platform, vm, texts, fallbacks = verifier.model(indices, verifier.vm_values(profile, output))
        result = dict(batch=str(batch.resolve()), fixture_only=True, original_constructor_executed=False)
    else:
        if summary['schema'] < 13:
            raise ValueError('Production property probe requires schema 13')
        with zipfile.ZipFile(summary['properties']['index']['path']) as z:
            platform, vm, texts = [list(map(json.loads, z.read(n).splitlines())) for n in ('platform.jsonl', 'vm.jsonl', 'strings.jsonl')]
            fallbacks = json.loads(z.read('fallbacks.json'))
        selector = module('property_source_selector', 'prepare-class-init-probe.py')
        owner = 'jdk/internal/util/SystemProps$Raw'
        roots = [('bootstrap', owner, '<init>', '()V'), ('bootstrap', owner, 'propDefault', '(I)Ljava/lang/String;'),
                 ('bootstrap', owner, 'platformProperties', '()[Ljava/lang/String;'), ('bootstrap', owner, 'vmProperties', '()[Ljava/lang/String;')]
        result = selector.prepare(batch, plan, output, [], roots)
        result['property_entries'] = {r['name']: r['symbol'] for r in result['requested_method_roots']}
        result['fixture_only'] = False
        (output/'closure.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    with (output/'properties-cases.bin').open('wb') as f:
        def integer(i): f.write(struct.pack('<i', i))
        def text(uu):
            integer(len(uu)); f.write(struct.pack('<'+'H'*len(uu), *uu))
        for i in (0x50524f42, c['id'], array['id'], field['offset'], len(texts)): integer(i)
        for t in texts: text(t['utf16'])
        integer(len(platform))
        for r in platform:
            for key in ('index', 'query', 'argument'): integer(r[key])
            integer(next(i for i, field in enumerate(raw['fields']) if field['name'] == r['name']))
            text(list(map(ord, r['name'])))
        integer(len(vm))
        for r in vm:
            integer(r['key_literal']); integer(r['value_literal'])
        integer(len(fallbacks))
        for i in fallbacks: integer(i)
    (output/'property-probe-input.json').write_text(json.dumps(dict(source_Raw_class_id=c['id'], source_array_type_id=array['id'],
        normal_String_layout=summary['string_literals']['source_layout'], fixture_only=fixture,
        platform_properties=len(platform), vm_pairs=len(vm), source_IR=source['identity']), indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch', type=Path); p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--ir', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--fixture', action='store_true')
    a = p.parse_args(); r = prepare(a.batch, a.plan, a.ir, a.output, a.fixture)
    print(json.dumps(dict(fixture_only=a.fixture, selected_Java_methods=len(r.get('selected_methods', {})),
                         selected_property_natives=len(r.get('selected_property_natives', {})))))
