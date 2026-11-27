"""Pure MASM service source for the separately verified owned-memory adapters."""
import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAGMENT = ROOT / 'native/providers/unsafe_owned_memory.asm.inc'
SERVICE_POOL_BYTES = 32
BUSY_MILLISECONDS = 2000


def module(name):
    spec = importlib.util.spec_from_file_location('owned_service_' + name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


C = module('unsafe-owned-memory-source')
SC = module('jimage-unsafe-read-source')
PUBLIC = {C.POOL, C.SERVICE, C.TYPED_SERVICE, 'boom_provider_owned_unsafe_bind',
    'boom_provider_owned_unsafe_unbind', 'boom_owned_unsafe_counters'}
PROCS = {'boom_native_memory_service', 'boom_primitive_heap_span', 'GetTickCount64', 'Sleep',
    'boom_heap_contains', 'boom_object_check', 'boom_runtime_row', 'boom_java_unsafe_jimage_memory',
    'boom_provider_jimage_copy_service', 'boom_threads_id_address'}
DATA = {'boom_java_unsafe_field_pool', 'boom_provider_thread_registry'}
FOREIGN = {'GetTickCount64', 'Sleep'}


def _prefix(name, native):
    _, prefix, checker, _, _ = SC.prefix_source()
    validator = checker.replace('uf_pool', name + '_pool').replace(name + '_pool_valid PROC\n', name + '_pool_valid PROC PRIVATE\n')
    declarations = '.const\n' + name + '_widths BYTE 1,1,2,2,4,8,4,8,8\n.code\n' + validator
    adapted = prefix.replace('um_', name + '_').replace('uf_pool_valid', name + '_pool_valid').replace('uf_widths', name + '_widths')
    adapted = adapted.replace(' sub rsp,56\n', ' sub rsp,328\n').replace(' .allocstack 56\n', ' .allocstack 328\n')
    if native:
        assert adapted.count(' .endprolog\n') == 1
        adapted = adapted.replace(' .endprolog\n', ' .endprolog\n'
            ' mov DWORD PTR [rsp+288],r9d\n mov QWORD PTR [rsp+296],r8\n'
            ' lea r8,boom_java_unsafe_field_pool\n mov r9d,5\n', 1)
    return declarations, adapted


def assembly(abi):
    assert abi['schema'] == 'boom-native-memory-owner-abi-v1' and abi['owner_bytes'] == abi['job_bytes'] == 128
    offsets = abi['job_offsets']
    fields = {'OWNER': 'owner_q', 'ADDRESS': 'address_q', 'BYTES': 'bytes_q', 'OTHER': 'other_q',
        'VALUE': 'value_q', 'RESULT': 'result_q', 'TOKEN': 'lease_token_q', 'WIDTH': 'width_d', 'FLAGS': 'flags_d', 'OP': 'op_d'}
    source = 'option casemap:none\n' + ''.join('EXTERN ' + name + (':PROC\n' if name in PROCS else ':BYTE\n') for name in sorted(PROCS | DATA))
    source += 'UOM_OWNER_MAGIC EQU 0' + abi['owner_magic'][2:] + 'h\n'
    source += 'UOM_BUSY_MILLISECONDS EQU ' + str(BUSY_MILLISECONDS) + '\n'
    source += ''.join('UOMJ_' + name + ' EQU ' + str(offsets[key]) + '\n' for name, key in fields.items())
    source += ('UOM_CLEAR_JOB MACRO displacement\n LOCAL clear_next\n'
        ' lea r10,[rsp+displacement]\n xor eax,eax\n mov ecx,16\nclear_next:\n'
        ' mov QWORD PTR [r10],rax\n add r10,8\n dec ecx\n jnz clear_next\nENDM\n'
        'UOM_UNWIND MACRO framebytes\n add rsp,framebytes\n'
        ' pop r15\n pop r14\n pop r13\n pop r12\n pop rbp\n pop rdi\n pop rsi\n pop rbx\nENDM\n')
    native_decl, native_prefix = _prefix('uom', True)
    typed_decl, typed_prefix = _prefix('uot', False)
    source += native_decl + typed_decl
    fragment = FRAGMENT.read_text(encoding='utf-8')
    assert fragment.count(';@NATIVE_RECEIVER_PREFIX@') == fragment.count(';@TYPED_RECEIVER_PREFIX@') == 1
    source += fragment.replace(';@NATIVE_RECEIVER_PREFIX@', native_prefix.rstrip()).replace(';@TYPED_RECEIVER_PREFIX@', typed_prefix.rstrip()) + '\nEND\n'
    return source, PUBLIC, PROCS | DATA


def metadata(abi, S):
    _, prefix, validator, _, _ = SC.prefix_source()
    return dict(schema=1, owner_ABI=abi, binding_pool=dict(symbol=C.POOL, bytes=32, magic=0x4e574f55, abi=1,
        owner=8, state=16, startup_only_bind=True, after_users_and_successful_owner_close_only_unbind=True,
        contains_Java_oops=False, native_root_spans=[]),
        exports=sorted(PUBLIC), imports=sorted(PROCS | DATA), foreign=sorted(FOREIGN),
        required_provider_families=['normal-thread-primitives-v1'],
        required_native_helper_symbols=['boom_native_memory_service', 'boom_primitive_heap_span',
            'boom_java_unsafe_jimage_memory', 'boom_provider_jimage_copy_service'],
        receiver_prefix=dict(source=S.artifact(ROOT / 'native/runtime/java_unsafe_fields.asm'),
            original_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(), original_validator_sha256=hashlib.sha256(validator.encode()).hexdigest(),
            native_forced_typed_kind_for_receiver_validation=5, width_validation_does_not_access_data=True,
            generated_frame_bytes=328, input_argv_and_semantic_op_preserved=True),
        primitive_arrays=dict(header_payload_byte_count=-16, multiply_header_by_element_size=False,
            tags=list(range(260, 268)), shifts=[0, 1, 2, 3, 0, 1, 2, 3], array_base_offset=0,
            endpoint_validator='boom_primitive_heap_span', heap_lifetime='caller maintains normal nonmoving quiescent-GC contract'),
        operations=dict(normal=['allocate', 'reallocate', 'free', 'set', 'copy', 'copySwap'],
            normal_heap_primitive_arrays=True, native_RW=True, heap_to_heap=True,
            legacy_5_RO_reads=True, legacy_RO_to_heap_byte_copy=True, RO_to_native_RW=False,
            native_volatile_CAS_reference=False, unknown_addresses=False),
        allocation_failures=dict(core_status_4_or_7='Return actual0 with clean Context so original Java constructs OOME',
            realloc_old_block_retained=True, VirtualFree_failure='Context20, all actual regions retained by core'),
        busy=dict(retry_only_status=2, deadline_milliseconds=BUSY_MILLISECONDS, real_Sleep_milliseconds=1,
            no_owner_lock_held_while_waiting=True, timeout='explicit development-limit Context20; no silent write success',
            other_errors_not_retried=True, shared_RPR_cancellation_protocol_added=False, synthetic_B002=False),
        lease_protocol=dict(all_heap_endpoints_validated_before_borrow=True, pure_MASM_physical_copy_while_native_borrow_held=True,
            release_after_every_acquired_nonzero_token=True, release_failure='Context20 and tracked live lease; owner close must fail busy',
            free_or_realloc_blocked_by_active_borrow=True),
        policies=dict(pending_Context_all32_bytes_unchanged=True, no_Context_clear_and_retry=True,
            original_ThreadIdentifiers_counter_checked_before_RW_for_plain_Long=True,
            typed_domain_miss_or_closed_delegates_to_original_RO_and_heap_counter_validation=True,
            no_Java_field_or_root_or_class_state_writes=True, new_GC_or_performance_claim=False),
        sources={name: S.artifact(ROOT / name) for name in ('scripts/unsafe-owned-memory-service-source.py',
            'native/providers/unsafe_owned_memory.asm.inc')}, registered=False, executed=False, game_started=False)
