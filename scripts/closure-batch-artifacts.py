"""Resolve retained batch modules for a source closure using an accepted derivation."""
import importlib.util
import hashlib
import json
from pathlib import Path


def module(file):
    spec = importlib.util.spec_from_file_location('closure_sparse_batch_source', Path(__file__).with_name(file))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def source_records(summary, resolve):
    """Allow only original records explicitly present in the certified summary."""
    records = {}
    def collect(value):
        if isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, dict):
            if 'path' in value and isinstance(value.get('digest'),dict):
                path = Path(value['path'])
                if path in records and records[path] != value['digest']:
                    raise ValueError('Conflicting certified artifact digest')
                records[path] = value['digest']
            for child in value.values():
                collect(child)
    collect(summary)
    def checked(root, record, subdirectory=''):
        path = Path(record['path'])
        if subdirectory and (Path(subdirectory).name != subdirectory or subdirectory in ('.','..')):
            raise ValueError('Expected a single batch module directory')
        if not path.is_absolute() or path not in records or records[path] != record['digest']:
            raise ValueError('Artifact absent from certified source summary or digest differs')
        return resolve(root,record,subdirectory)
    return checked


def configure(coff, batch, summary, plan=None):
    """Bind only this verifier instance. Ordinary batches keep their fixed-root resolver."""
    batch = Path(batch).resolve()
    derivation = batch / 'unsafe-field-derivation.json'
    boot = batch / 'boot-unnamed-derivation.json'
    if boot.is_file():
        if derivation.exists():
            raise ValueError('Conflicting sparse derivation kinds')
        provider = module('refresh-boot-unnamed-batch.py')
        resolve, identity = provider.verified_resolver(batch,summary,plan)
        identity = dict(identity, closure_resolver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        coff.artifact = source_records(summary,resolve)
        return identity
    if not derivation.exists():
        receipt = batch / 'verification.json'
        artifacts = Path(__file__).resolve().parents[1] / '.boom'
        if batch.parent in (artifacts/'unsafe-field-batches',artifacts/'boot-unnamed-batches') or (
                receipt.is_file() and any(k.startswith('sparse_') for k in json.loads(receipt.read_bytes()))):
            raise ValueError('Missing source batch derivation')
        return None
    source = module('refresh-unsafe-field-batch.py')
    check = source.CHECK
    data = source.read(derivation)
    parent = Path(data['base_batch']).resolve()
    recorded_plan = Path(data['plan']).resolve()
    check(batch.is_relative_to(source.ART) and parent.is_relative_to(source.ART) and parent != batch and
          recorded_plan.is_relative_to(source.ART) and (plan is None or Path(plan).resolve() == recorded_plan),
          'Unexpected sparse source roots or translation plan')
    full_path = batch / 'verification.json'
    full = source.read(full_path)
    scope = full.get('sparse_original_vm_image_home')
    check(isinstance(scope, dict) and full.get('verified') is True and
          all(full.get(k, {}).get('verified') is True for k in ('unsafe_fields','unsafe_memory','class_lookup','frames','properties')),
          'A full sparse source batch verification is required')
    check(data['accepted_base']['summary'] == scope['base_summary'] and data['derivative'] == scope['derived_summary'] and
          source.artifact(batch / 'summary.json') == data['derivative'] and summary == source.read(batch / 'summary.json'),
          'Selected sparse summary differs from full verification')
    accepted = data['accepted_base']
    base, original_plan, receipts = source.locked_base(parent, recorded_plan, accepted['summary']['digest']['sha256'],
                                                       accepted['verification']['digest']['sha256'])
    check(receipts == accepted and data['input_fingerprint'] == base['input_fingerprint'] == summary['input_fingerprint'] and
          data['ir_identity'] == base['ir_identity'] == summary['ir_identity'] and scope == source.vm_image_home_scope(data,batch),
          'Sparse producer, source plan, or original VM home differs')
    index, assembly, _, inputs = source.reconstruct(parent, recorded_plan, base, original_plan)
    before = base['unsafe_fields']['units'][index]
    after = summary['unsafe_fields']['units'][index]
    change = dict(unit=index, original_assembly=before['assembly'], original_object=before['object'],
                  assembly=after['assembly'], object=after['object'])
    counter = data.get('thread_counter')
    init = data.get('class_initialization')
    check(data['schema'] == (3 if init else 2 if counter else 1) and (not init or counter) and
          data['source_inputs'] == inputs and data['replacements'] == [change] and data['source_metadata_reconstructed'] is True and
          data['all_other_summary_fields_equal'] is True and data['original_Java_units_recompiled'] == 0,
          'Sparse original source or declared replacement differs')
    kernel = data['kernel']['current']
    check(kernel == source.artifact(source.ROOT / source.KERNEL) and
          summary == source.derived(base,index,after['assembly'],after['object'],kernel['digest']['sha256'],counter,init),
          'Sparse summary changes exceed the certified dependency and UFMP refresh')
    if counter:
        check(counter['current'] == source.artifact(source.ROOT / 'native/runtime/thread_registry.asm'),
              'Sparse thread registry source differs')
    if init:
        for name in ('native/runtime/classes32.asm','native/runtime/unwind.asm'):
            check(init['sources'][name]['current'] == source.artifact(source.ROOT / name),'Sparse class initialization source differs')
    resolve = source.sparse_artifacts(parent,batch)
    asm = resolve(batch,after['assembly'],'unsafe-fields')
    obj = resolve(batch,after['object'],'unsafe-fields')
    old = resolve(batch,before['object'],'unsafe-fields')
    check(asm.parent == obj.parent == batch / 'unsafe-fields' and old.parent == parent / 'unsafe-fields' and
          asm.read_bytes() == assembly and source.normalized_coff(old,1) == source.normalized_coff(obj,2),
          'Sparse UFMP ASM or COFF differs from verified original source')
    identity = dict(scope='certified_source_batch_and_one_UFMP_derivative',producer=str(parent),batch=str(batch),
                    plan=accepted['plan'],base_summary=accepted['summary'],base_verification=accepted['verification'],
                    derived_summary=data['derivative'],derivation=source.artifact(derivation),full_verification=source.artifact(full_path),
                    tools={name:source.artifact(Path(__file__).with_name(name))['digest']['sha256'] for name in
                           ('closure-batch-artifacts.py','refresh-unsafe-field-batch.py','verify-batch-assembly.py',
                            'verify-batch-unsafe-fields.py','verify-batch-frames.py')})
    coff.artifact = source_records(summary,resolve)
    return identity
