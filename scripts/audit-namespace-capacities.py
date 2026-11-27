"""Check UFMP capacity guards in a verified native image's assembly units.

Derive the expected type capacity from the linked UFMP2 pool source. Check
every *_UFMP_TYPES constant against it, including its explicit pool+8 guard.
This is a static source consistency check; it never executes or modifies an
image, recompiles Java, or grants runtime acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
POOL = re.compile(
    rb'^boom_java_unsafe_field_pool\s+DWORD\s+0*55464d50h\s*,\s*2\s*,\s*(\d+)\s*,',
    re.IGNORECASE,
)
CONSTANT = re.compile(
    rb'^\s*([A-Za-z_][A-Za-z_0-9]*_UFMP_TYPES)\s+EQU\s+(\d+)\s*(?:;.*)?$',
    re.IGNORECASE,
)
GUARD = re.compile(
    rb'^\s*cmp\s+DWORD\s+PTR\s*\[[A-Za-z_0-9]+\s*\+\s*8\s*\]\s*,\s*'
    rb'([A-Za-z_][A-Za-z_0-9]*_UFMP_TYPES)\s*(?:;.*)?$',
    re.IGNORECASE,
)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), digest=dict(size=path.stat().st_size, sha256=digest))


def checked(record):
    actual = artifact(record['path'])
    check(actual == record, 'Artifact identity changed: ' + str(record['path']))
    return Path(actual['path'])


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def scan_units(units):
    """Inspect explicit assembly units; return all recognized consumer checks."""
    pools, consumers, source_pins = [], [], []
    assembly_count = 0
    for unit in units:
        pin = unit.get('assembly')
        if pin is None:
            continue
        role = unit['role']
        path = Path(pin['path']).resolve()
        hasher, size = hashlib.sha256(), 0
        definitions, guards = {}, {}
        with path.open('rb') as stream:
            for number, raw in enumerate(stream, 1):
                hasher.update(raw)
                size += len(raw)
                line = raw.rstrip(b'\r\n')
                pool = POOL.match(line)
                if pool:
                    check('boom_java_unsafe_field_pool' in unit['exports'],
                          'UFMP source is not exported by its linked unit')
                    pools.append(dict(role=role, assembly=pin, line=number,
                                      type_capacity=int(pool.group(1))))
                constant = CONSTANT.fullmatch(line)
                if constant:
                    name = constant.group(1).decode('ascii')
                    check(name not in definitions, 'Duplicate namespace constant: ' + name)
                    definitions[name] = dict(constant=name, value=int(constant.group(2)),
                                             definition_line=number)
                guard = GUARD.fullmatch(line)
                if guard:
                    name = guard.group(1).decode('ascii')
                    guards.setdefault(name, []).append(number)
        check(size == pin['digest']['size'] and hasher.hexdigest() == pin['digest']['sha256'],
              'Assembly identity changed while scanning: ' + str(path))
        check(set(guards) <= definitions.keys(), 'UFMP guard has no local constant: ' + role)
        for name, definition in definitions.items():
            check(name in guards, 'UFMP constant has no recognized pool+8 guard: ' + name)
            consumers.append(dict(role=role, assembly=pin, **definition,
                                  guard_lines=guards[name]))
        assembly_count += 1
        source_pins.append(pin)
    check(len(pools) == 1, 'Exactly one linked UFMP2 pool source is required')
    capacity = pools[0]['type_capacity']
    check(0 < capacity < 1 << 31, 'UFMP2 type capacity is out of range')
    for consumer in consumers:
        consumer['expected_type_capacity'] = capacity
        consumer['matches_pool'] = consumer['value'] == capacity
    return dict(
        schema=1,
        scope='linked_assembly_UFMP2_type_capacity_guard_consistency_only',
        namespace_consistent=all(row['matches_pool'] for row in consumers),
        actual_units=len(units), assembly_units=assembly_count,
        readonly_units=len(units) - assembly_count,
        pool=pools[0], consumers=consumers, assembly_inputs=source_pins,
        stale_guard_count=sum(not row['matches_pool'] for row in consumers),
        sources_or_objects_modified=False, native_or_Java_executed=False,
        full_PE_verification_repeated=False, runtime_acceptance_complete=False,
    )


def audit(args):
    image_pin, proof_pin = artifact(args.image), artifact(args.proof)
    check(image_pin['digest']['sha256'] == args.image_sha256 and
          proof_pin['digest']['sha256'] == args.proof_sha256,
          'Explicit image or independent proof identity differs')
    image, proof = read(args.image), read(args.proof)
    check(proof['verified'] is True and proof['full_PE_byte_equal'] is True and
          proof['overlay'] == image_pin and image['linked'] is True,
          'An independently verified linked native image is required')
    check(proof['actual_object_count'] == len(image['objects']) and
          proof['actual_units'] == len(image['units']),
          'Independent object/unit counts differ')
    image_inputs = {row['path']: row for row in image['inputs']}
    proof_inputs = {row['path']: row for row in proof['current_required_inputs']}
    for unit in image['units']:
        check(unit['object'] in image['objects'], 'A unit object is absent from the image')
        if 'assembly' in unit:
            pin = unit['assembly']
            check(image_inputs.get(pin['path']) == pin and proof_inputs.get(pin['path']) == pin,
                  'Unit source is not bound by the actual image and independent proof')
    for record in [image['executable'], image['runtime'], *image['objects']]:
        checked(record)
    result = scan_units(image['units'])
    result.update(image=image_pin, independent_native_verification=proof_pin,
                  producer=artifact(__file__), actual_image_and_object_identities_checked=True)
    output = args.output.resolve()
    check(any(output.is_relative_to(ROOT / name) for name in ('.boom', 'target', 'dist')),
          'Audit output must stay in a project-generated directory')
    check(not output.exists(), 'Preserve existing audit reports')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(report=artifact(output), namespace_consistent=result['namespace_consistent'],
                          type_capacity=result['pool']['type_capacity'],
                          consumers=len(result['consumers']), stale_guard_count=result['stale_guard_count'])))
    return 0 if result['namespace_consistent'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'proof', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('image-sha256', 'proof-sha256'):
        parser.add_argument('--' + name, required=True)
    raise SystemExit(audit(parser.parse_args()))
