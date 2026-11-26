"""Summarize actual generated contracts and remaining protocols; no execution."""
import argparse
import json
from pathlib import Path
import zipfile


def summarize(batch):
    batch = Path(batch)
    summary = json.loads((batch/'summary.json').read_text(encoding='utf-8'))
    verification = json.loads((batch/'verification.json').read_text(encoding='utf-8'))
    if summary['schema'] < 6 or not verification.get('dispatch', {}).get('verified'):
        raise ValueError('A verified schema 6 batch is required')
    with zipfile.ZipFile(summary['dispatch']['index']['path']) as bundle:
        gaps = list(map(json.loads, bundle.read('gaps.jsonl').splitlines()))
        targets = list(map(json.loads, bundle.read('targets.jsonl').splitlines()))
    groups = [dict(kind=g['kind'], protocol=g['protocol'], symbols=len(g['symbols']),
                   affected_methods=len(g['affected_methods']), native_method=g['native_method'],
                   example_symbols=list(g['examples'])) for g in gaps]
    groups.sort(key=lambda g: (-g['symbols'], -g['affected_methods'], g['kind'], g['protocol']))
    pending_targets = [t for t in targets if not t['java_assembly_emitted'] and not t['native_binding_provided']]
    return dict(schema=1, batch=str(batch.resolve()), priority_basis='whole_input_impact_not_startup_reachability',
                generated_Class_bootstrap=({k:v for k,v in summary['class_bootstrap'].items() if k not in ('units','index')} if summary['schema']>=15 else None),
                generated_Unsafe_bootstrap=({k:v for k,v in summary['unsafe_bootstrap'].items() if k not in ('units','index')} if summary['schema']>=16 else None),
                generated_VM_registration=({k:v for k,v in summary['vm_registration'].items() if k not in ('units','index')} if summary['schema']>=17 else None),
                generated_Runtime_resources=({k:v for k,v in summary['runtime_resources'].items() if k not in ('units','index')} if summary['schema']>=18 else None),
                generated_bitcasts=({k:v for k,v in summary['bitcasts'].items() if k not in ('units','index')} if summary['schema']>=19 else None),
                generated_Unsafe_fields=({k:v for k,v in summary['unsafe_fields'].items() if k not in ('units','index')} if summary['schema']>=20 else None),
                generated_Class_lookup=({k:v for k,v in summary['class_lookup'].items() if k not in ('units','index')} if summary['schema']>=22 else None),
                generated_Unsafe_memory=({k:v for k,v in summary['unsafe_memory'].items() if k not in ('units','index')} if summary['schema']>=21 else None),
                generated_String_concat=({k:v for k,v in summary['string_concat'].items() if k not in ('units','index')} if summary['schema']>=14 else None),
                generated_properties=({k:v for k,v in summary['properties'].items() if k not in ('units','index')} if summary['schema']>=13 else None),
                generated_String_intern=({k:v for k,v in summary['string_intern'].items() if k not in ('units','index')} if summary['schema']>=12 else None),
                generated_Class_literals=({k:v for k,v in summary['class_literals'].items() if k not in ('units','index')} if summary['schema']>=10 else None),
                java_methods=summary['counts'], generated_array_clones=({k:v for k,v in summary['array_clone'].items() if k not in ('units','index')}
                    if summary['schema']>=7 else None), generated_dispatch={k: v for k, v in summary['dispatch'].items()
                    if k not in ('units', 'index')}, unresolved_symbols=verification['unresolved_unique_symbols'],
                unresolved_categories=verification['unresolved_categories'], pending_protocol_groups=groups,
                pending_dispatch_targets=pending_targets, method_codegen_failures=summary['diagnostics'],
                linked=False, runtime_abi_verified=False, game_started=False, world_created=False,
                automatic_gc=False, full_game_ready=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('batch', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.batch)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), generated_dispatch_sites=result['generated_dispatch']['generated_sites'],
                         pending_groups=len(result['pending_protocol_groups']), unresolved_symbols=result['unresolved_symbols'],
                         game_started=False), ensure_ascii=False))
