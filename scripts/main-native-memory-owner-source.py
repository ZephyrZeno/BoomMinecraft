"""Pure MASM process lifecycle for the independent writable-memory owner.

This source producer adds no Java classes or method IDs. The caller must prove
the six Unsafe bindings, the original source selection and every linked object.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAGMENT = ROOT / 'native/probe/main_native_memory_owner.asm.inc'
EXPORTS = {'boom_main_native_memory_prepare', 'boom_main_native_memory_close',
    'boom_main_native_memory_write_report', 'boom_main_native_memory_owner',
    'boom_main_native_memory_report'}
PROCS = {'boom_native_memory_init', 'boom_native_memory_close',
    'boom_provider_owned_unsafe_bind', 'boom_provider_owned_unsafe_unbind',
    'CreateFileW', 'WriteFile', 'CloseHandle', 'GetLastError'}
DATA = {'boom_owned_unsafe_counters'}
REPORT_BYTES = 320
REPORT = dict(magic=0, abi=4, bytes=8, flags=12, initialize_status=16,
    bind_status=20, close_status=24, unbind_status=28, state_before=32,
    state_after=36, live_before=40, live_after=48, leases_before=56,
    leases_after=64, logical_bytes_before=72, logical_bytes_after=80,
    metadata_bytes_before=88, metadata_bytes_after=96, budget=104,
    capacity=112, os_error=116, allocations=120, frees=128, resizes=136,
    context_preserved=144, cleanup_status=148, context_before=160,
    context_after=192, service_counters=224, token_sequence=272)


def check(value, message):
    if not value:
        raise ValueError(message)


def assembly(abi, capacity=4096, budget=1073741824):
    check(abi['owner_bytes'] == 128 and abi['version'] == 1 and
        abi['owner_states'] == {'closed': 3, 'draining': 2, 'ready': 1} and
        abi['close_requires_no_leases'] is True and abi['Java_oop_roots'] is False,
        'Exact plain-memory owner lifecycle ABI required')
    check(type(capacity) is int and 1 <= capacity <= 4096 and
        type(budget) is int and 0 < budget < 1 << 63, 'Explicit process owner limits required')
    fields = ('state', 'live', 'active', 'logical_bytes', 'metadata_bytes',
        'budget', 'capacity', 'os_error', 'allocations', 'frees', 'resizes', 'sequence')
    source = 'option casemap:none\n'
    source += ''.join('EXTERN ' + name + ':PROC\n' for name in sorted(PROCS))
    source += ''.join('EXTERN ' + name + ':QWORD\n' for name in sorted(DATA))
    source += 'MM_CAPACITY EQU ' + str(capacity) + '\nMM_BUDGET EQU ' + str(budget) + '\n'
    source += ''.join('MMO_' + name.upper() + ' EQU ' + str(abi['owner_offsets'][name]) + '\n' for name in fields)
    source += FRAGMENT.read_text(encoding='utf-8') + '\nEND\n'
    return source, set(EXPORTS), PROCS | DATA


def derive(entry):
    """Apply four reversible additions to the already repaired Main entry."""
    check(isinstance(entry, str) and '\r' not in entry, 'Exact LF native entry required')
    check('vpe_post_signal_threads_closed:\n' in entry, 'The worker/Signal shutdown repair must precede this transform')
    check('boom_main_native_memory_' not in entry, 'Writable owner hooks already exist')
    original, edits = entry, []

    def replace(name, before, after):
        nonlocal entry
        check(entry.count(before) == 1, 'Missing or ambiguous native lifecycle anchor: ' + name)
        entry = entry.replace(before, after, 1)
        edits.append(dict(name=name, before=before, after=after))

    declaration = 'EXTERN boom_main_jimage_prepare:PROC\n'
    replace('imports', declaration, ''.join('EXTERN ' + name + ':PROC\n' for name in
        ('boom_main_native_memory_prepare', 'boom_main_native_memory_close',
         'boom_main_native_memory_write_report')) + declaration)
    before = ' call boom_main_jimage_prepare\n'
    replace('initialize_and_bind_before_Java', before,
        ' call boom_main_native_memory_prepare\n test eax,eax\n jz vpe_native_memory_ready\n'
        ' mov DWORD PTR [boom_vm_entry_report+68],eax\n jmp vpe_capture\n'
        'vpe_native_memory_ready:\n' + before)
    before = (' call boom_main_jimage_resources_close\n test eax,eax\n jz vpe_report\n'
        ' mov DWORD PTR [boom_vm_entry_report+68],eax\n'
        ' cmp DWORD PTR [boom_vm_entry_report+80],86\n je vpe_report\n'
        ' mov DWORD PTR [boom_vm_entry_report+80],70\nvpe_report:\n')
    replace('close_only_after_heap_and_JIMAGE_release', before,
        before.replace(' jz vpe_report\n', ' jz vpe_native_memory_close\n', 1).replace('vpe_report:\n',
        ' jmp vpe_report\nvpe_native_memory_close:\n lea rcx,boom_vm_entry_context\n'
        ' call boom_main_native_memory_close\n test eax,eax\n jz vpe_report\n'
        ' mov DWORD PTR [boom_vm_entry_report+68],eax\n'
        ' cmp DWORD PTR [boom_vm_entry_report+80],86\n je vpe_report\n'
        ' mov DWORD PTR [boom_vm_entry_report+80],70\nvpe_report:\n'))
    before = 'vpe_report:\n call boom_main_jimage_write_report\n'
    replace('additional_CREATE_NEW_report', before,
        'vpe_report:\n call boom_main_native_memory_write_report\n test eax,eax\n'
        ' jz vpe_native_memory_report_done\n mov DWORD PTR [boom_vm_entry_report+68],eax\n'
        ' cmp DWORD PTR [boom_vm_entry_report+80],86\n je vpe_native_memory_report_done\n'
        ' mov DWORD PTR [boom_vm_entry_report+80],74\nvpe_native_memory_report_done:\n'
        ' call boom_main_jimage_write_report\n')
    check(inverse(entry, edits) == original, 'Native lifecycle inverse must recover every original byte')
    return entry, edits


def inverse(entry, edits):
    for edit in reversed(edits):
        check(entry.count(edit['after']) == 1, 'Ambiguous inverse native lifecycle delta')
        entry = entry.replace(edit['after'], edit['before'], 1)
    return entry
