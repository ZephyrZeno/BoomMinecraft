"""Build source-bound, family-sized completion tasks from verified translation.

This is an offline development tool. A task describes missing semantics; it is
never an implementation, a default-return stub, or evidence of game execution.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile


def check(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def artifact(record):
    path = Path(record['path'])
    check(path.stat().st_size == record['digest']['size'] and
          digest(path) == record['digest']['sha256'], 'Completion source artifact changed: ' + str(path))
    return path


def rows(bundle, name):
    with bundle.open(name) as stream:
        for line in stream:
            yield json.loads(line)


def method_id(symbol):
    match = re.fullmatch(r'boom_m(\d+)(?:_body)?', symbol)
    return int(match[1]) if match else None


def family(kind, protocol, declaration=None):
    """Group a semantic rule, retaining every exact protocol in its task.

    Names are scheduling hints only. In particular, a familiar bootstrap name
    does not prove its implementation, loader identity, or ABI compatibility.
    """
    if declaration is not None:
        symbol = declaration['symbol']
        owner = symbol['loader'] + ':' + symbol['owner']
        if declaration['code_sha256'] is not None:
            return 'java-code:' + owner, 'source_or_backend_rule'
        if declaration['access'] & 0x100:
            return 'native:' + owner, 'assembly_runtime_rule'
        return 'declaration:' + owner, 'method_selection_or_missing_implementation'
    if kind in ('invokedynamic', 'dynamic_constant'):
        # Preserve the signature after grouping overloads under their owner.
        owner = protocol.split('(', 1)[0].rsplit('.', 1)[0]
        return 'bootstrap:' + owner, 'bootstrap_lowering_rule'
    if kind == 'signature_polymorphic_native':
        return 'signature-polymorphic', 'method_handle_or_var_handle_rule'
    if kind == 'literal_resolution':
        return 'literal:' + protocol, 'literal_factory_rule'
    return kind + ':' + protocol, 'source_contract_rule'


def validate_frontier(frontier, summary, summary_sha, classes_sha):
    check(frontier.get('source_input_fingerprint') == summary['input_fingerprint'] and
          frontier.get('batch_ir_identity') == summary['ir_identity'] and
          frontier.get('source_classes_sha256') == classes_sha and
          frontier.get('source_batch_summary_sha256') == summary_sha,
          'Entry scan batch/IR/source identity differs; scan the current batch again')
    check(frontier.get('game_started') is False and frontier.get('System_boot_phases_completed') is False,
          'A static scan must not claim execution')


def build_tasks(gaps, targets, declarations, frontier=None, available_dispatch=frozenset(),provided_native_ids=frozenset()):
    tasks = {}
    symbol_task = {}
    available = []

    def add(kind, protocol, symbols, methods=(), declaration=None, origin='direct_contract'):
        key, action = family(kind, protocol, declaration)
        task = tasks.setdefault(key, dict(id=key, action=action, status='requires_semantic_implementation',
            protocols=set(), symbols=set(), affected_methods=set(), declarations={}, origins=set(),
            entry_frontier_symbols=set()))
        task['protocols'].add(protocol)
        task['symbols'].update(symbols)
        task['affected_methods'].update(methods)
        task['origins'].add(origin)
        if declaration is not None:
            task['declarations'][declaration['id']] = declaration
        for symbol in symbols:
            previous = symbol_task.setdefault(symbol, key)
            check(previous == key, 'Conflicting completion rule for ' + symbol)
        return task

    for gap in gaps:
        declaration = declarations[gap['native_method']] if gap['native_method'] is not None else None
        if declaration is not None:
            check(gap['kind'] == 'native_declaration' and declaration['access'] & 0x100 and
                  declaration['code_sha256'] is None, 'Native gap differs from original declaration')
            if declaration['id'] in provided_native_ids:
                check(gap['symbols']==[f"boom_m{declaration['id']}"],'Provider cannot remove a different source contract symbol')
                continue
        add(gap['kind'], gap['protocol'], gap['symbols'], gap['affected_methods'], declaration)
    for target in targets:
        if target['java_assembly_emitted'] or target['native_binding_provided']:
            continue
        declaration = declarations[target['method']]
        check(target['class_sha256'] == declaration['class_sha256'] and
              (target['class_id'], target['defining_loader'], target['owner'], target['name'], target['descriptor'], target['access']) ==
              (declaration['class_id'], declaration['symbol']['loader'], declaration['symbol']['owner'],
               declaration['symbol']['name'], declaration['symbol']['descriptor'], declaration['access']),
              'Dispatch target differs from source declaration')
        symbol = declaration['symbol']
        if target['method'] in provided_native_ids:
            check(declaration['code_sha256'] is None and declaration['access']&0x100,'Provider cannot replace a Java dispatch target')
            continue
        add('method', symbol['loader'] + ':' + symbol['owner'] + '.' + symbol['name'] + symbol['descriptor'],
            [f"boom_m{target['method']}"], declaration=declaration, origin='unprovided_dispatch_target')
    for gap in (frontier or {}).get('frontiers', []):
        symbol = gap['symbol']
        if symbol in symbol_task:
            tasks[symbol_task[symbol]]['entry_frontier_symbols'].add(symbol)
            continue
        binding = gap.get('binding') or {}
        declaration = declarations.get(method_id(symbol))
        if method_id(symbol) in provided_native_ids and symbol==f'boom_m{method_id(symbol)}':
            check(declaration is not None and declaration['code_sha256'] is None and declaration['access']&0x100,'Provider frontier is not a source native')
            available.append(dict(symbol=symbol,action='select_verified_runtime_provider',reason=gap['reason']))
            continue
        # A direct-only scan can stop at a provider that already exists.
        if gap['kind'] == 'virtual_dispatch' and symbol in available_dispatch:
            available.append(dict(symbol=symbol, action='expand_existing_static_dispatch', reason=gap['reason']))
            continue
        task = add(gap['kind'], binding.get('protocol') or gap['kind'], [symbol],
                   [binding['caller_method']] if 'caller_method' in binding else [], declaration,
                   origin='entry_static_frontier')
        task['entry_frontier_symbols'].add(symbol)
    result = []
    for task in tasks.values():
        task = dict(task)
        task['declarations'] = sorted(task['declarations'].values(), key=lambda d: d['id'])
        for name in ('protocols', 'symbols', 'affected_methods', 'origins', 'entry_frontier_symbols'):
            task[name] = sorted(task[name])
        task['symbol_count'] = len(task['symbols'])
        task['entry_frontier_count'] = len(task['entry_frontier_symbols'])
        # Static inclusion is an analysis priority, never proof of a boot path.
        task['priority_basis'] = ('entry_static_inclusion' if task['entry_frontier_count'] else 'whole_input_impact')
        result.append(task)
    result.sort(key=lambda t: (not bool(t['entry_frontier_count']), -t['entry_frontier_count'],
                               -t['symbol_count'], -len(t['affected_methods']), t['id']))
    return result, available


def compare(previous, current):
    identity = ('input_fingerprint', 'ir_identity', 'entry_scope', 'requested_roots')
    check(all(previous.get(k) == current.get(k) for k in identity),
          'Previous completion worklist uses different inputs or scan roots/scope')
    before = {s for task in previous['tasks'] for s in task['symbols']}
    after = {s for task in current['tasks'] for s in task['symbols']}
    return dict(removed_requests=sorted(before - after), added_requests=sorted(after - before),
                same_missing_requests=before == after,
                previous_compiler_sha256=previous['compiler_sha256'],
                removed_requests_prove_execution=False)


def plan(batch, source_plan, frontier_path=None, previous_path=None,provider_paths=None):
    batch, source_plan = Path(batch), Path(source_plan)
    summary_path = batch / 'summary.json'
    summary, verification, original = read(summary_path), read(batch / 'verification.json'), read(source_plan / 'summary.json')
    check(summary['schema'] >= 10 and verification.get('verified') and verification.get('dispatch', {}).get('verified'),
          'A fully verified schema 10 batch is required')
    check(summary['input_fingerprint'] == original['input_fingerprint'], 'Batch/source plan identity differs')
    classes_path = artifact(original['artifacts']['classes'])
    classes = list(map(json.loads, classes_path.read_text(encoding='utf-8').splitlines()))
    classes_sha = original['artifacts']['classes']['digest']['sha256']
    summary_sha = digest(summary_path)
    frontier = read(frontier_path) if frontier_path else None
    if frontier is not None:
        validate_frontier(frontier, summary, summary_sha, classes_sha)
    with zipfile.ZipFile(artifact(summary['dispatch']['index'])) as bundle:
        gaps, targets = list(rows(bundle, 'gaps.jsonl')), list(rows(bundle, 'targets.jsonl'))
        available_dispatch = {r['label'] for r in rows(bundle, 'sites.jsonl') if r['diagnostic'] is None}
    check(len(gaps) == verification['dispatch']['pending_contract_groups'], 'Verified gap group count differs')
    wanted = {g['native_method'] for g in gaps if g['native_method'] is not None}
    wanted.update(t['method'] for t in targets if not t['java_assembly_emitted'] and not t['native_binding_provided'])
    wanted.update(id_ for g in (frontier or {}).get('frontiers', []) if (id_ := method_id(g['symbol'])) is not None)
    declarations = {}
    source_methods = original['artifacts']['methods']
    stream_sha = hashlib.sha256()
    size = 0
    with Path(source_methods['path']).open('rb') as stream:
        for line in stream:
            stream_sha.update(line)
            size += len(line)
            # Read the source inventory once, retaining only needed declarations.
            method = json.loads(line)
            if method['id'] in wanted:
                owner = classes[method['class_id']]
                check(method['id'] in owner['method_ids'] and method['class_sha256'] == owner['origin']['sha256'] and
                      method['symbol']['owner'] == owner['name'] and method['symbol']['loader'] == owner['origin']['loader'],
                      'Source method/class identity differs')
                declarations[method['id']] = {k: method[k] for k in
                    ('id', 'class_id', 'symbol', 'class_sha256', 'code_sha256', 'access')}
    check(size == source_methods['digest']['size'] and stream_sha.hexdigest() == source_methods['digest']['sha256'],
          'Source method inventory changed')
    check(declarations.keys() == wanted, 'A requested method is missing from the source plan')
    packs=[];provided_ids=frozenset();provider_module=None
    if provider_paths:
        spec=importlib.util.spec_from_file_location('completion_verified_providers',Path(__file__).with_name('verify-runtime-provider-pack.py'))
        provider_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider_module)
        packs=provider_module.load_packs(batch,source_plan,provider_paths);provided_ids=frozenset(m['method'] for p in packs for m in p['manifest']['methods'])
    tasks, available = build_tasks(gaps, targets, declarations, frontier, available_dispatch,provided_ids)
    pending = {s for task in tasks for s in task['symbols']}
    check(sum(t['symbol_count'] for t in tasks) == len(pending), 'Duplicate requests across completion tasks')
    diagnostics = summary['diagnostics']
    check(sum(d['methods'] for d in diagnostics) == summary['counts']['failed_methods'], 'Codegen failure accounting differs')
    result = dict(schema=1, batch=str(batch.resolve()), input_fingerprint=summary['input_fingerprint'],
        ir_identity=summary['ir_identity'], compiler_sha256=summary['compiler_sha256'],
        source_batch_summary_sha256=summary_sha, source_classes_sha256=classes_sha,
        source_methods_sha256=source_methods['digest']['sha256'],
        verification_sha256=digest(batch / 'verification.json'), dispatch_index_sha256=summary['dispatch']['index']['digest']['sha256'],
        verification_is_assumed_from_checked_pipeline=True,
        mode='offline_completion_planning', generated_Java_methods=summary['counts']['assembly_emitted'],
        java_methods=summary['counts']['java_methods'], failed_Java_methods=summary['counts']['failed_methods'],
        java_codegen_groups=diagnostics, java_codegen_groups_are_not_additional_unique_requests=True,
        entry_scope=frontier['scope'] if frontier else None,
        requested_roots=({k: frontier[k] for k in ('requested_class_roots', 'requested_method_roots', 'requested_contract_roots')}
                         if frontier else None),
        entry_frontier_symbols=len(frontier['frontiers']) if frontier else None,
        entry_frontier_requests_accounted=(sum(t['entry_frontier_count'] for t in tasks) + len(available)) if frontier else None,
        existing_provider_actions=available, existing_provider_action_count=len(available),
        tasks=tasks, task_count=len(tasks), pending_request_symbols=len(pending),
        task_categories=dict(sorted(Counter(t['action'] for t in tasks).items())),
        unresolved_link_symbols=verification['unresolved_unique_symbols'],
        coverage_scope='all_dispatch_protocol_gaps_and_unprovided_dispatch_targets_plus_selected_entry_frontiers',
        unknown_dynamic_targets_expanded=False, runtime_linkage_closure_verified=False,
        automatic_semantic_synthesis=False, linked=False, game_started=False, world_created=False, full_game_ready=False,
        stop_reason='requires_semantic_rules' if tasks or diagnostics else 'static_requests_clear_execution_still_required')
    if frontier is not None:
        check(result['entry_frontier_requests_accounted'] == result['entry_frontier_symbols'],
              'An entry frontier request was lost')
    if packs:result.update(runtime_provider_packs=provider_module.references(packs),source_native_providers=len(provided_ids),
        base_batch_modified=False,base_Java_codegen_rerun=False,unresolved_link_symbol_count_scope='base_batch_only_not_effective_provider_link_closure')
    if previous_path:
        result['comparison'] = compare(read(previous_path), result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--frontiers', type=Path)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--provider-pack',type=Path,action='append',default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = plan(args.batch, args.plan, args.frontiers, args.previous,args.provider_pack)
    # Publish only a complete worklist; a failed source check leaves no partial result.
    temporary = args.output.with_name(args.output.name + '.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(args.output)
    print(json.dumps({k: result[k] for k in ('task_count', 'pending_request_symbols', 'task_categories',
          'entry_frontier_symbols', 'existing_provider_action_count', 'stop_reason', 'game_started')}, ensure_ascii=False))
