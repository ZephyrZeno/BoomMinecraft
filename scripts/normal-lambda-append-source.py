"""Append normal Lambda source identities while preserving an explicit prefix.

append() is the source projection API: existing generated records and Class
references are retained, new requests are validated by normal-lambda-source,
and the existing Class writer supplies their bytes. No verifier, assembler,
linker, Java process, or runtime registration is executed by this module.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tomllib
import zipfile

MODULES = {}


def check(value, message):
    if not value:
        raise ValueError(message)


def installed_root():
    for path in Path(__file__).resolve().parents:
        cargo = path / 'Cargo.toml'
        if (cargo.is_file() and (path / 'scripts/constructor-provider-source.py').is_file()
                and (path / 'native/runtime/java_classes.asm').is_file()):
            with cargo.open('rb') as stream:
                if tomllib.load(stream).get('package', {}).get('name') == 'boom-minecraft':
                    return path
    raise ValueError('Installed project source/tool root not found')


def module(name):
    if name not in MODULES:
        key = 'lambda_append_' + name.replace('-', '_')
        spec = importlib.util.spec_from_file_location(key, installed_root() / 'scripts' / (name + '.py'))
        value = importlib.util.module_from_spec(spec)
        sys.modules[key] = value
        spec.loader.exec_module(value)
        MODULES[name] = value
    return MODULES[name]


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=digest))


def checked(row):
    actual = artifact(row['path'])
    check(all(actual['digest'][key] == row['digest'][key] for key in ('size', 'sha256')),
          'Explicit source artifact changed: ' + row['path'])
    if 'sha1' in row['digest']:
        with Path(actual['path']).open('rb') as stream:
            check(hashlib.file_digest(stream, 'sha1').hexdigest() == row['digest']['sha1'],
                  'Explicit source artifact SHA1 changed: ' + row['path'])
    return Path(actual['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def source_inputs(batch, plan):
    """Use the maintained original Class, loader, type and member source API."""
    return module('normal-lambda-source').Sources(Path(batch), Path(plan))


def request_contract(sources, request):
    C = module('normal-lambda-source')
    if set(request) == {'host_class', 'constant'}:
        ident, constant = request['host_class'], request['constant']
        check(type(ident) is int and 0 <= ident < len(sources.classes) and
              type(constant) is int and constant > 0, 'Invalid source site request')
        return C.site(sources, sources.classes[ident], constant)
    check(isinstance(request, dict) and isinstance(request.get('host'), dict),
          'Request must be a source site selector or the complete original site contract')
    ident, constant = request['host']['class_id'], request['constant']
    check(type(ident) is int and 0 <= ident < len(sources.classes), 'Original host Class ID outside source')
    actual = C.site(sources, sources.classes[ident], constant)
    check(actual == request, 'Requested original source contract differs from the maintained site rule')
    return actual


def append(sources, prefix, requests, selection, *, prefix_reference, prefix_verification,
           prefix_verification_reference, selection_reference, source_verification,
           source_verification_reference, generated_path):
    """Return (aggregate_manifest, {generated_name: Class_bytes}) without writes.

    generated_path(name) provides explicit references for newly generated Class
    bytes. Existing prefix references remain exactly as supplied. Existing paths
    are checked for byte identity; absent paths are output references whose
    contents are returned, and are not described as verified machine artifacts.
    """
    C = module('normal-lambda-source')
    check(prefix['source_rule'] == artifact(installed_root() / 'scripts/normal-lambda-source.py') and
          prefix['policy'] == C.POLICY and
          prefix['scope'] == 'normal_lambda_sparse_expansion_source_and_generated_classfiles_only',
          'Prefix compiler rule, policy or source scope differs')
    check(prefix_verification['verified'] is True and prefix_verification['expansion'] == prefix_reference,
          'Explicit prefix source verification differs')
    check(sources.base == prefix['base'], 'Generated prefix belongs to another original source batch')
    check(source_verification['verified'] is True and
          source_verification['closure_manifest_sha256'] == selection_reference['digest']['sha256'] and
          selection['source_batch_summary_sha256'] == sources.base['batch_summary']['digest']['sha256'] and
          selection['source_classes_sha256'] == sources.base['source_classes']['digest']['sha256'],
          'Complete original-source verification must bind this source and original Class plan')
    ranges = dict(classes=len(sources.classes), types=sources.summary['runtime_metadata']['type_capacity'],
                  methods=sum(len(cls['method_ids']) for cls in sources.classes),
                  fields=sources.summary['runtime_metadata']['field_capacity'])
    check(prefix['original_ranges'] == ranges, 'Original identity ranges differ')
    generated = copy.deepcopy(prefix['generated'])
    next_field = ranges['fields']
    names, bindings = set(), set()
    for ordinal, row in enumerate(generated):
        checked(row['class_file'])
        check(row['type_id'] == row['class_id'] == ranges['types'] + ordinal and
              [m['id'] for m in row['methods']] == list(range(ranges['methods'] + 3*ordinal, ranges['methods'] + 3*ordinal + 3)),
              'Prefix generated type or method identities are not dense and ordered')
        fields = row['layout']['fields']
        check([f['id'] for f in fields] == list(range(next_field, next_field + len(fields))),
              'Prefix generated field identities differ')
        next_field += len(fields)
        check(row['contract']['generated_name'] not in names and row['contract']['binding_label'] not in bindings,
              'Duplicate generated prefix site or Class')
        names.add(row['contract']['generated_name'])
        bindings.add(row['contract']['binding_label'])
    check(prefix['appended_ranges'] == dict(types=[ranges['types'], ranges['types'] + len(generated)],
          methods=[ranges['methods'], ranges['methods'] + 3*len(generated)], fields=[ranges['fields'], next_field]),
          'Prefix appended ranges differ')
    validated = []
    for request in requests:
        contract = request_contract(sources, request)
        check(contract['binding_label'] not in bindings and contract['generated_name'] not in names,
              'Requested site collides with an existing generated Class or site')
        bindings.add(contract['binding_label'])
        names.add(contract['generated_name'])
        validated.append(contract)
    check(validated, 'At least one new source-accepted site is required')
    validated.sort(key=lambda row: (row['host']['origin']['loader'], row['host']['class_id'], row['constant']))
    parent = sources.lookup('bootstrap', 'java/lang/Object')
    object_ctor = C.source_member(sources, parent, '<init>', '()V')
    for member in [object_ctor] + [row['implementation_member'] for row in validated]:
        selected = selection['selected_methods'].get(str(member['method']))
        check(selected and (selected['class_id'], selected['source_sha256'], selected['code_sha256']) ==
              (member['class_id'], member['class_sha256'], member['code_sha256']) and
              selection['selected_function_sha256'].get('boom_m' + str(member['method']) + '_body'),
              'Original constructor or implementation must already have selected original Code and a provided body')
    selected_classes = {row['class_id']: row for row in selection['selected_classes']}
    for contract in validated:
        row = selected_classes.get(contract['bootstrap_member']['class_id'])
        check(row and row['diagnostic'] is None, 'Original bootstrap Class initialization must be selected normally')
    with zipfile.ZipFile(checked(sources.summary['class_literals']['index'])) as archive:
        mirrors = {row['type_id']: row for line in archive.open('types.jsonl') if (row := json.loads(line))}
    blobs = {}
    for contract in validated:
        ordinal = len(generated)
        type_id, method_id = ranges['types'] + ordinal, ranges['methods'] + 3*ordinal
        blob = C.generated_class(contract)
        raw = C.I.Source(blob)
        path = Path(generated_path(contract['generated_name'])).resolve()
        if path.exists():
            check(path.is_file() and path.read_bytes() == blob, 'Explicit generated Class reference has different bytes')
        class_ref = dict(path=str(path), digest=dict(size=len(blob), sha256=hashlib.sha256(blob).hexdigest()))
        captures = [dict(id=next_field+i, index=i, name='c'+str(i), descriptor=descriptor, offset=i*8,
                         reference=True, storage_bytes=8) for i, descriptor in enumerate(contract['captures'])]
        next_field += len(captures)
        host = contract['host']
        origin = dict(loader=host['origin']['loader'], binary_name=contract['generated_name'].replace('/', '.'),
            source_id='boom:'+C.RULE, jar_entry='<generated>/'+contract['generated_name']+'.class',
            java_class_major=65, sha256=class_ref['digest']['sha256'], generated=dict(generator=C.RULE, abi=1,
                host_loader=host['origin']['loader'], host_class=host['name'], host_source_id=host['origin']['source_id'],
                host_sha256=host['origin']['sha256'], host_method=contract['source_instruction']['method'],
                host_Code_sha256=contract['source_instruction']['code_sha256'], site=contract['constant'],
                pc=contract['source_instruction']['pc']))
        methods = []
        for offset, member in enumerate(raw.methods):
            body = raw.code(member)
            methods.append(dict(id=method_id+offset, class_id=type_id, name=member['name'], descriptor=member['descriptor'],
                access=member['access'], code_length=len(body['bytes']), code_sha256=hashlib.sha256(body['bytes']).hexdigest(),
                frame_flags=4|16|int(member['name']=='<init>'), original=False))
        interface = sources.types[contract['interface']['class_id']]
        mirror = dict(mirrors[host['class_id']], type_id=type_id, superclass=parent['id'], component=None,
                      flags=(mirrors[host['class_id']]['flags']&1)|2, raw_access=raw.access, major=65)
        generated.append(dict(contract=contract, class_file=class_ref, origin=origin, type_id=type_id, class_id=type_id,
            runtime_class_name=C.runtime_class_name(contract, type_id),
            layout=dict(abi=2, payload_bytes=len(captures)*8, reference_prefix=len(captures), fields=captures),
            type=dict(id=type_id, kind=1, marker_flags=0, parent_component=parent['id'],
                ancestors=sorted({parent['id'], interface['id']} | set(interface['ancestors'])),
                defining_loader=host['origin']['loader'], name=contract['generated_name'], source_sha256=origin['sha256']),
            class_mirror=mirror, methods=methods, new_arrays=[], array_of_generated_class_supported=False,
            class_initialization_state_initial=0, class_failure_root_initial=0, additional_instance_roots=False,
            object_constructor=object_ctor))
        blobs[contract['generated_name']] = blob
    manifest = copy.deepcopy(prefix)
    manifest.update(tool=artifact(__file__), generated=generated, rejected=[],
        appended_ranges=dict(types=[ranges['types'], ranges['types']+len(generated)],
            methods=[ranges['methods'], ranges['methods']+3*len(generated)], fields=[ranges['fields'], next_field]),
        prefix_expansion=prefix_reference, prefix_source_verification=prefix_verification_reference,
        preserved_prefix_classes=len(prefix['generated']), newly_appended_sites=len(validated),
        original_source_manifest=selection_reference, original_source_full_verification=source_verification_reference,
        append_api=artifact(__file__), assembled=False, linked=False, executed=False, game_started=False)
    check(manifest['generated'][:len(prefix['generated'])] == prefix['generated'], 'Generated prefix mutated')
    return manifest, blobs


def assembly(manifest, sources):
    """Render with the maintained normal assembly backend, without invoking MASM."""
    text = module('normal-lambda-assembly').module(manifest, sources)
    definitions = {row[1] for row in re.finditer(r'(?m)^(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|BYTE|WORD)\b)', text)}
    references = set(re.findall(r'\bboom_\w+\b', text)) - definitions
    calls = set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_\w+)\b', text))
    return 'option casemap:none\n' + ''.join('EXTERN '+name+':'+('PROC' if name in calls else 'BYTE')+'\n'
        for name in sorted(references)) + text + '\nEND\n'


def output_target(value):
    target, root = Path(value).resolve(), installed_root()
    check(any(target.is_relative_to(root / name) for name in ('.boom', 'target', 'dist')),
          'Generated output must stay in the installed project .boom, target or dist')
    check(not target.exists(), 'Generated output must be create-new')
    return target


def project(prefix_file, prefix_verification_file, requests, batch, plan, selection_file,
            source_verification_file, generated_path):
    """File-input wrapper for append(); it reads inputs but creates no outputs."""
    sources = source_inputs(batch, plan)
    manifest, blobs = append(sources, read(prefix_file), requests, read(selection_file),
        prefix_reference=artifact(prefix_file), prefix_verification=read(prefix_verification_file),
        prefix_verification_reference=artifact(prefix_verification_file), selection_reference=artifact(selection_file),
        source_verification=read(source_verification_file), source_verification_reference=artifact(source_verification_file),
        generated_path=generated_path)
    return manifest, blobs, sources


def main(args):
    output = output_target(args.output)  # Must precede source-input reads.
    requested = read(args.requests)
    requests = requested if isinstance(requested, list) else [requested]
    def generated_path(name):
        path = (output / 'generated' / (name + '.class')).resolve()
        check(path.is_relative_to(output / 'generated'), 'Generated internal Class name escapes output')
        return path
    manifest, blobs, sources = project(args.prefix, args.prefix_verification, requests, args.batch, args.plan,
        args.selection, args.source_verification, generated_path)
    text = assembly(manifest, sources)
    output.mkdir(parents=True)
    for name, blob in blobs.items():
        path = generated_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(blob)
    with (output / 'expansion.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(manifest, stream, indent=2); stream.write('\n')
    with (output / 'adapters.asm').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    print(json.dumps(dict(expansion=artifact(output / 'expansion.json'), adapters=artifact(output / 'adapters.asm'),
                          source_only=True, machine_or_behavior_verified=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prefix', 'prefix-verification', 'requests', 'batch', 'plan', 'selection', 'source-verification', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    main(parser.parse_args())
