"""Plan shared IR expansion from the actual pending invokedynamic sites.

This is a build-time design/preflight tool, not a code generator. A structurally
recognized site still needs access/type checks, an implemented expander, source
verification, assembly, linkage and execution. It never supplies a missing body.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOOKUP = 'Ljava/lang/invoke/MethodHandles$Lookup;'
METHOD_TYPE = 'Ljava/lang/invoke/MethodType;'
CALL_SITE = 'Ljava/lang/invoke/CallSite;'
STRING = 'Ljava/lang/String;'
OBJECT = 'Ljava/lang/Object;'
CONCAT = 'java/lang/invoke/StringConcatFactory'
LAMBDA = 'java/lang/invoke/LambdaMetafactory'
RECORD = 'java/lang/runtime/ObjectMethods'
BOOTSTRAPS = {
    (CONCAT, 'makeConcat'): f'({LOOKUP}{STRING}{METHOD_TYPE}){CALL_SITE}',
    (CONCAT, 'makeConcatWithConstants'): f'({LOOKUP}{STRING}{METHOD_TYPE}{STRING}[{OBJECT}){CALL_SITE}',
    (LAMBDA, 'metafactory'): f'({LOOKUP}{STRING}{METHOD_TYPE}{METHOD_TYPE}Ljava/lang/invoke/MethodHandle;{METHOD_TYPE}){CALL_SITE}',
    (LAMBDA, 'altMetafactory'): f'({LOOKUP}{STRING}{METHOD_TYPE}[{OBJECT}){CALL_SITE}',
    (RECORD, 'bootstrap'): f'({LOOKUP}{STRING}Ljava/lang/invoke/TypeDescriptor;Ljava/lang/Class;{STRING}[Ljava/lang/invoke/MethodHandle;){OBJECT}',
}


def check(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_artifact(record):
    path = Path(record['path'])
    check(path.stat().st_size == record['digest']['size'] and sha(path) == record['digest']['sha256'],
          'Source artifact changed: ' + str(path))
    return path


def take_type(text, start, allow_void=False):
    check(start < len(text), 'Truncated descriptor')
    position = start
    while position < len(text) and text[position] == '[':
        position += 1
    dimensions = position - start
    check(dimensions <= 255 and position < len(text), 'Invalid array descriptor')
    kind = text[position]
    if kind == 'L':
        end = text.find(';', position + 1)
        check(end > position + 1, 'Invalid object descriptor')
        name = text[position + 1:end]
        check(not any(c in name for c in '.;[\x00') and not name.startswith('/') and
              not name.endswith('/') and '//' not in name, 'Invalid internal class name')
        position = end + 1
    else:
        check(kind in 'ZBCSIJFD' or (kind == 'V' and allow_void and not dimensions),
              'Invalid primitive/void descriptor')
        position += 1
    return text[start:position], position


def signature(text):
    check(isinstance(text, str) and text.startswith('('), 'Invalid method descriptor')
    args, position = [], 1
    while position < len(text) and text[position] != ')':
        arg, position = take_type(text, position)
        args.append(arg)
    check(position < len(text) and text[position] == ')', 'Missing descriptor result')
    result, position = take_type(text, position + 1, True)
    check(position == len(text) and sum(width(a) for a in args) <= 255, 'Invalid method descriptor suffix/slots')
    return args, result


def width(ty):
    return 2 if ty in ('J', 'D') else 1


def reference(ty):
    return ty.startswith(('L', '['))


def constant(cls, index, kind):
    value = cls['constants'].get(str(index))
    check(isinstance(value, dict) and len(value) == 1, 'Missing source constant')
    check(kind in value, 'Unexpected source constant kind; expected ' + kind)
    return value[kind]


def candidate(rule, expansion, **details):
    return dict(classification='structural_candidate', proposed_rule=rule, expansion=expansion,
                expander_implemented=False, semantic_compatibility_verified=False, **details)


def deferred(rule, reason):
    return dict(classification='compatibility_case', proposed_rule=rule, reason=reason,
                expander_implemented=False, semantic_compatibility_verified=False)


def concat_plan(cls, site):
    args, result = signature(site['descriptor'])
    if result != STRING or sum(width(a) for a in args) > 200:
        return deferred('concat-v1', 'concat_result_or_200_slot_contract')
    constants = site['arguments']
    if site['bootstrap']['name'] == 'makeConcat':
        if constants:
            return deferred('concat-v1', 'unexpected_makeConcat_constants')
        recipe, values = [1] * len(args), []
    else:
        if not constants or 'StringUtf16' not in cls['constants'].get(str(constants[0]), {}):
            return deferred('concat-v1', 'recipe_not_static_String')
        recipe = constant(cls, constants[0], 'StringUtf16')
        values = [cls['constants'][str(c)] for c in constants[1:]]
        if any('StringUtf16' not in c for c in values):
            return deferred('concat-v1', 'bootstrap_constant_requires_link_time_conversion')
        values = [v['StringUtf16'] for v in values]
    if recipe.count(1) != len(args) or recipe.count(2) != len(values):
        return deferred('concat-v1', 'recipe_marker_arity')
    parts, literal, dynamic, static = [], [], 0, 0
    for unit in recipe:
        check(isinstance(unit, int) and 0 <= unit <= 65535, 'Invalid UTF16 recipe unit')
        if unit == 1:
            if literal:
                parts.append(dict(literal_utf16=literal))
                literal = []
            parts.append(dict(argument=dynamic, descriptor=args[dynamic]))
            dynamic += 1
        elif unit == 2:
            literal.extend(values[static])
            static += 1
        else:
            literal.append(unit)
    if literal:
        parts.append(dict(literal_utf16=literal))
    return candidate('concat-v1', 'ordinary_IR_and_normal_String_services', arguments=args, parts=parts,
                     reference_conversions='String_conversion_in_dynamic_argument_order',
                     required_checks=['bootstrap_loader_and_access', 'normal_String_layout',
                                      'left_to_right_conversion_and_exception_order',
                                      'float_double_formatting', 'overflow_OOM_and_allocation_identity',
                                      'active_roots_and_exception_edges'])


def lambda_plan(cls, site):
    values = site['arguments']
    if len(values) < 3:
        return deferred('lambda-v1', 'lambda_bootstrap_arity')
    sam = constant(cls, values[0], 'MethodType')
    impl = constant(cls, values[1], 'Handle')
    dynamic = constant(cls, values[2], 'MethodType')
    markers, bridges, serializable = [], [], False
    if site['bootstrap']['name'] == 'metafactory':
        if len(values) != 3:
            return deferred('lambda-v1', 'metafactory_extra_constants')
    else:
        if len(values) < 4:
            return deferred('lambda-v1', 'altMetafactory_missing_flags')
        flags = constant(cls, values[3], 'Int')
        if flags < 0 or flags & ~7:
            return deferred('lambda-v1', 'unknown_altMetafactory_flags')
        serializable, position = bool(flags & 1), 4
        for flag, kind, collection in ((2, 'Class', markers), (4, 'MethodType', bridges)):
            if flags & flag:
                if position >= len(values):
                    return deferred('lambda-v1', 'truncated_altMetafactory_list')
                count = constant(cls, values[position], 'Int')
                position += 1
                if count < 0 or position + count > len(values):
                    return deferred('lambda-v1', 'invalid_altMetafactory_count')
                collection.extend(constant(cls, c, kind) for c in values[position:position + count])
                position += count
        if position != len(values):
            return deferred('lambda-v1', 'altMetafactory_trailing_constants')
    captured, iface = signature(site['descriptor'])
    sam_args, sam_ret = signature(sam)
    dynamic_args, dynamic_ret = signature(dynamic)
    target, target_ret = signature(impl['descriptor'])
    kind = impl['reference_kind']
    if kind not in (5, 6, 7, 8, 9) or not iface.startswith('L'):
        return deferred('lambda-v1', 'lambda_implementation_or_interface_shape')
    if kind in (5, 7, 9):
        target = ['L' + impl['owner'] + ';'] + target
    if kind == 8:
        if target_ret != 'V' or impl['name'] != '<init>' or impl['interface']:
            return deferred('lambda-v1', 'constructor_handle_shape')
        target_ret = 'L' + impl['owner'] + ';'
    if len(sam_args) != len(dynamic_args) or len(captured) + len(dynamic_args) != len(target):
        return deferred('lambda-v1', 'lambda_parameter_arity')
    if any(a != b and not (reference(a) and reference(b)) for a, b in zip(sam_args, dynamic_args)):
        return deferred('lambda-v1', 'SAM_instantiated_primitive_parameters_differ')
    if sam_ret != dynamic_ret and not (reference(sam_ret) and reference(dynamic_ret)):
        return deferred('lambda-v1', 'SAM_instantiated_primitive_return_differs')
    for bridge in bridges:
        signature(bridge)
    details = dict(captured=captured, interface=iface, SAM=site['name'], SAM_descriptor=sam,
                   instantiated_descriptor=dynamic, implementation=impl,
                   effective_implementation_arguments=target, effective_implementation_return=target_ret,
                   marker_interfaces=markers, bridge_descriptors=bridges, serializable=serializable,
                   bound_receiver_null_check=kind in (5, 7, 9) and bool(captured),
                   required_checks=['loader_nest_access_and_method_selection', 'SAM_and_marker_interfaces',
                                    'capture_assignability', 'boxing_unboxing_casts_and_primitive_widening',
                                    'normal_generated_class_layout_and_type_registration',
                                    'dispatch_default_methods_and_bridges', 'active_roots_and_exception_edges'])
    if serializable:
        return dict(deferred('lambda-v1', 'SerializedLambda_and_deserialization_contract'), shape=details)
    return candidate('lambda-v1', 'generated_normal_class_and_ordinary_IR', **details)


def record_plan(cls, site):
    components = cls['record_components']
    if components is None or cls['superclass'] != 'java/lang/Record' or cls['access'] & 0x610 != 0x10:
        return deferred('record-v1', 'record_source_shape')
    owner = cls['name']
    expected = {'equals': f'(L{owner};{OBJECT})Z', 'hashCode': f'(L{owner};)I',
                'toString': f'(L{owner};){STRING}'}
    if site['descriptor'] != expected.get(site['name']):
        return deferred('record-v1', 'record_operation_descriptor')
    values = site['arguments']
    if len(values) != len(components) + 2 or constant(cls, values[0], 'Class') != owner:
        return deferred('record-v1', 'record_component_class_or_arity')
    # Bootstrap presentation names survive Minecraft field obfuscation. They
    # are not field identities, and equals/hashCode ignore this argument.
    names = constant(cls, values[1], 'StringUtf16')
    display_names = [] if not names else [[]]
    for unit in names:
        if unit == 59:
            display_names.append([])
        else:
            display_names[-1].append(unit)
    if site['name'] == 'toString' and (len(display_names) != len(components) or any(not n for n in display_names)):
        return deferred('record-v1', 'record_display_name_arity')
    for (name, descriptor), index in zip(components, values[2:]):
        handle = constant(cls, index, 'Handle')
        if (handle['reference_kind'], handle['owner'], handle['name'], handle['descriptor'], handle['interface']) != (1, owner, name, descriptor, False):
            return deferred('record-v1', 'noncanonical_record_getter')
        field = next((f for f in cls['fields'] if (f['name'], f['descriptor']) == (name, descriptor)), None)
        # The handle names the real instance field. Visibility may be widened
        # by the shipped class transform; private is not a bootstrap invariant.
        if field is None or field['access'] & 0x08:
            return deferred('record-v1', 'record_field_access')
    return candidate('record-v1', 'ordinary_IR_with_source_field_access', operation=site['name'],
                     components=components, bootstrap_display_names_utf16=names,
                     display_names_ignored=site['name'] != 'toString',
                     required_checks=['bootstrap_loader_and_private_access', 'exact_record_type_identity',
                                      'NaN_canonicalization_and_signed_zero', 'reference_equals_hash_and_string_conversion',
                                      'active_roots_and_exception_edges'])


def expand_shape(cls, site):
    bootstrap = site['bootstrap']
    owner, name = bootstrap['owner'], bootstrap['name']
    rule = {CONCAT: 'concat-v1', LAMBDA: 'lambda-v1', RECORD: 'record-v1'}.get(owner)
    if rule is None:
        return deferred('unregistered', 'no_proposed_expander_for_' + owner)
    if (bootstrap['reference_kind'] != 6 or bootstrap['interface'] or
            bootstrap['descriptor'] != BOOTSTRAPS.get((owner, name))):
        return deferred(rule, 'bootstrap_handle_or_exact_signature')
    return {CONCAT: concat_plan, LAMBDA: lambda_plan, RECORD: record_plan}[owner](cls, site)


def inspect_shard(job):
    shard, requests = job
    path = checked_artifact(shard['zip'])
    result = []
    with zipfile.ZipFile(path) as bundle:
        for entry in shard['entries']:
            wanted = requests.get(entry['class_id'])
            if not wanted:
                continue
            data = bundle.read(entry['path'])
            check(len(data) == entry['digest']['size'] and hashlib.sha256(data).hexdigest() == entry['digest']['sha256'],
                  'IR class payload changed')
            cls = json.loads(data)
            check(cls['class_id'] == entry['class_id'] and cls['origin']['sha256'] == entry['class_sha256'],
                  'IR class origin changed')
            uses = defaultdict(list)
            for method in cls['methods']:
                for instruction in (method['body'] or {}).get('instructions', []):
                    cp = (instruction['operand'].get('Constant')
                          if isinstance(instruction['operand'], dict) else None)
                    if instruction['opcode'] == 186 and cp in wanted:
                        uses[cp].append(dict(method=method['id'], code_sha256=method['code_sha256'], pc=instruction['pc']))
            for cp, (symbol, protocol) in sorted(wanted.items()):
                site = constant(cls, cp, 'InvokeDynamic')
                bootstrap = site['bootstrap']
                check(protocol == bootstrap['owner'] + '.' + bootstrap['name'] + bootstrap['descriptor'] and uses[cp],
                      'Pending contract differs from actual source invokedynamic')
                result.append(dict(symbol=symbol, caller_class=cls['class_id'], constant=cp,
                    loader=cls['origin']['loader'], owner=cls['name'], class_sha256=cls['origin']['sha256'],
                    bootstrap=bootstrap, descriptor=site['descriptor'], source_uses=uses[cp], **expand_shape(cls, site)))
    return result


def plan(batch, ir, workers=4):
    started = time.monotonic()
    batch, ir = Path(batch), Path(ir)
    summary, source = read(batch / 'summary.json'), read(ir / 'summary.json')
    verification = read(batch / 'verification.json')
    check(verification.get('verified') and verification.get('dispatch', {}).get('verified'), 'Verified batch required')
    check(summary['input_fingerprint'] == source['input_fingerprint'] and summary['ir_identity'] == source['identity'],
          'Batch/IR input identity differs')
    index = checked_artifact(source['index'])
    dispatch = checked_artifact(summary['dispatch']['index'])
    requests, families = defaultdict(dict), Counter()
    with zipfile.ZipFile(dispatch) as bundle:
        for line in bundle.read('gaps.jsonl').splitlines():
            gap = json.loads(line)
            if gap['kind'] != 'invokedynamic':
                continue
            families[gap['protocol']] += len(gap['symbols'])
            for symbol in gap['symbols']:
                match = re.fullmatch(r'boom_batch_call_(\d+)_(\d+)_186', symbol)
                check(match is not None, 'Unsupported pending invokedynamic symbol')
                cls, cp = map(int, match.groups())
                check(cp not in requests[cls], 'Duplicate pending source site')
                requests[cls][cp] = symbol, gap['protocol']
    jobs, class_id, shard_count = [], 0, 0
    with index.open(encoding='utf-8') as stream:
        for shard_count, line in enumerate(stream, 1):
            shard = json.loads(line)
            check(shard['id'] == shard_count - 1 and shard['entries'], 'Invalid shard sequence')
            for entry in shard['entries']:
                check(entry['class_id'] == class_id, 'IR class inventory not contiguous')
                class_id += 1
            subset = {e['class_id']: requests[e['class_id']] for e in shard['entries'] if e['class_id'] in requests}
            if subset:
                jobs.append((shard, subset))
    check(class_id == source['classes'] and shard_count == source['shards'], 'IR index coverage differs')
    if workers == 1:
        groups = map(inspect_shard, jobs)
        sites = [site for group in groups for site in group]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            sites = [site for group in executor.map(inspect_shard, jobs) for site in group]
    sites.sort(key=lambda s: (s['caller_class'], s['constant']))
    check(len(sites) == sum(families.values()), 'Pending site coverage differs')
    totals = defaultdict(Counter)
    for site in sites:
        totals[site['proposed_rule']][site['classification']] += 1
    result = dict(schema=1, mode='protocol_expansion_design_preflight',
        input_fingerprint=summary['input_fingerprint'], ir_identity=summary['ir_identity'],
        source_batch_summary_sha256=sha(batch / 'summary.json'), source_ir_summary_sha256=sha(ir / 'summary.json'),
        source_ir_index_sha256=source['index']['digest']['sha256'],
        source_dispatch_index_sha256=summary['dispatch']['index']['digest']['sha256'],
        source_verification_sha256=sha(batch / 'verification.json'),
        planner_sha256=sha(Path(__file__)), input_IR_verification_assumed_from_checked_pipeline=True,
        workers=workers, elapsed_ms=round((time.monotonic()-started)*1000), pending_invokedynamic_sites=len(sites),
        rules={k: dict(v) for k, v in sorted(totals.items())}, protocols=dict(sorted(families.items())),
        compatibility_reasons=dict(sorted(Counter(s['reason'] for s in sites if 'reason' in s).items())),
        recognized_shapes_are_not_semantic_or_execution_proof=True,
        expanders_implemented=False, assembly_emitted=False, linked=False, game_started=False,
        world_created=False, runtime_linkage_closure_verified=False,
        coverage_scope='pending_invokedynamic_only_not_native_or_all_runtime_services')
    return result, sites


def publish(output, result, sites):
    output = Path(output).resolve()
    check(output.is_relative_to((ROOT / '.boom').resolve()), 'Output must be in this project .boom directory')
    check(not output.exists(), 'Use a fresh output directory to preserve previous evidence')
    output.mkdir(parents=True)
    sites_path = output / 'sites.jsonl'
    with sites_path.open('w', encoding='utf-8', newline='\n') as stream:
        for site in sites:
            stream.write(json.dumps(site, ensure_ascii=True, separators=(',', ':')) + '\n')
    result['sites'] = dict(path=str(sites_path), digest=dict(size=sites_path.stat().st_size, sha256=sha(sites_path)))
    with tempfile.NamedTemporaryFile(dir=output, delete=False, suffix='.tmp', mode='w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
        temporary = Path(stream.name)
    temporary.replace(output / 'summary.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path)
    parser.add_argument('--ir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 17))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result, sites = plan(args.batch, args.ir, args.workers)
    publish(args.output, result, sites)
    print(json.dumps({k: result[k] for k in ('pending_invokedynamic_sites', 'rules', 'compatibility_reasons', 'elapsed_ms',
                                           'expanders_implemented', 'assembly_emitted', 'game_started')}, ensure_ascii=True))
