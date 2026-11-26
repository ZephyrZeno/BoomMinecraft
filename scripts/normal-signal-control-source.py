"""Original Signal natives and Java callbacks over an attached VM OS worker."""
import hashlib
import re

KERNELS = ['signal_control.asm', 'signal_natives.asm', 'thread_registry.asm',
           'java_properties.asm', 'objects.asm', 'heap.asm', 'monitors.asm',
           'classes32.asm', 'field_address.asm', 'frames.asm']
FOREIGN = {'GetLastError'}
POLICY = dict(normal_source_layouts=True, platform='Windows', transport_config_abi=2,
    transport_config_bytes=64, Java_dispatch='original_Signal_dispatch',
    dispatcher_thread='original_Thread_constructor_and_current_OS_attachment',
    dispatcher_exit='original_Thread_exit_then_VM_terminal_publication_and_detach',
    native_handler_registration=True, signal_raise=True, VM_BREAK_thread_dump=False,
    unsupported_VM_BREAK='explicit_error', automatic_gc=False, all_native_frames=False)


def kernel(S):
    text = (S.ROOT/'native/providers/normal_signal_control.asm.inc').read_text(encoding='utf-8')
    imports = set(re.findall(r'(?m)^EXTERN (\w+):PROC$', text))
    return re.sub(r'(?m)^EXTERN \w+:PROC\n', '', text), imports


def java_contract(owner, raw, name, descriptor, access, S):
    S.check(owner['origin']['loader'] == 'bootstrap' and owner['origin']['source_id'] == 'jdk:java.base'
            and not owner['origin'].get('generated') and len(raw) == len(owner['method_ids']),
            'Signal upcalls require original bootstrap Java classes')
    found = [(i, m) for i, m in zip(owner['method_ids'], raw)
             if (m['name'], m['descriptor']) == (name, descriptor)]
    S.check(len(found) == 1 and found[0][1]['access'] == access and found[0][1]['code'] is not None,
            'Signal Java upcall flags/Code differ: '+name)
    i, method = found[0]
    return dict(method=i, class_id=owner['id'], owner=owner['name'], name=name, descriptor=descriptor,
        access=access, class_sha256=owner['origin']['sha256'],
        code_sha256=hashlib.sha256(method['code'][0]).hexdigest())


def index(summary, classes, S):
    L = S.module('signal_control_lookup_contracts', 'signal-lookup-source.py')
    T = S.module('signal_control_thread_contracts', 'normal-thread-start-source.py')
    R = S.module('signal_control_original_reader', 'verify-batch-frames.py')
    signal, thread = L.index(summary, classes, S), T.index(summary, classes, S)
    methods = [dict(row, operation=i) for i, row in enumerate(signal['unavailable_natives'])]
    owner, thread_class = classes[methods[0]['class_id']], classes[thread['thread_class']]
    upcalls = []
    for c, name, desc, flags in [(owner, 'dispatch', '(I)V', 0xa),
            (thread_class, '<init>', '(Ljava/lang/ThreadGroup;Ljava/lang/String;)V', 1),
            (thread_class, 'exit', '()V', 2)]:
        actual, raw = R.original_methods(S.original_class(summary, c))
        S.check(actual == c['name'], 'Signal callback original owner differs')
        upcalls.append(java_contract(c, raw, name, desc, flags, S))
    names = {(c['origin']['loader'], c['name']): c for c in classes}
    dependencies = sorted({owner['id'], thread['thread_class'], thread['holder_class'],
        names['bootstrap', 'java/lang/ThreadGroup']['id'], names['bootstrap', 'java/lang/String']['id']})
    return dict(schema=1, methods=methods, upcalls=upcalls, required_class_ids=dependencies,
        thread_class=thread['thread_class'], holder_class=thread['holder_class'],
        fields=[f for f in thread['fields'] if f['name'] in ('tid', 'eetop', 'holder', 'threadStatus')],
        dispatcher_name='Signal Dispatcher', pool_bytes=256, pool_abi=1,
        native_pool_bytes=64, native_pool_abi=1, transport_config_bytes=64, transport_config_abi=2,
        source_transform_chain='original_locked_no_transforms', game_started=False)


def data(m):
    calls = {c['name']: c for c in m['upcalls']}
    fields = {f['name']: f for f in m['fields']}
    pointers = ['boom_heap_ptr', 'boom_provider_thread_registry', 'boom_trace_pool',
        'boom_provider_signal_native_pool', f"boom_t{m['thread_class']}",
        f"boom_layout{m['thread_class']}", f"boom_m{calls['<init>']['method']}",
        f"boom_m{calls['exit']['method']}", f"boom_m{calls['dispatch']['method']}"]
    pointers += [f"boom_field_map{fields[n]['map_id']}" for n in ('tid', 'eetop', 'holder', 'threadStatus')]
    out = '.data?\nALIGN 8\nPUBLIC boom_provider_signal_roots\nboom_provider_signal_roots QWORD 2 DUP(?)\n'
    out += 'PUBLIC boom_provider_signal_failure\nboom_provider_signal_failure QWORD 4 DUP(?)\n'
    out += '.const\nPUBLIC boom_provider_signal_root_count\nboom_provider_signal_root_count QWORD 2\n'
    out += 'signal_dispatcher_name WORD '+','.join(str(ord(c)) for c in m['dispatcher_name'])+'\n'
    out += '.data\nALIGN 8\nPUBLIC boom_provider_signal_pool\nboom_provider_signal_pool DWORD 05349474Eh,1,0,0\n'
    out += ''.join(' QWORD OFFSET '+p+'\n' for p in pointers)
    out += ' QWORD OFFSET boom_provider_signal_roots,0,0,0,0,0\n DWORD 0,0\n'
    out += ' QWORD OFFSET boom_provider_signal_failure,0,0,0,0,0,OFFSET boom_java_vm_properties_pool,0,0,0\n'
    out += 'PUBLIC boom_provider_signal_native_pool\nboom_provider_signal_native_pool DWORD 0504E4753h,1\n'
    out += ' QWORD 0,0,0,OFFSET boom_trace_pool,0,0,0\n'
    out += 'signal_dispatcher_config DWORD 053474346h,2\n'
    out += ' QWORD OFFSET sig_dispatch,OFFSET sig_break,OFFSET boom_provider_signal_pool,0,0,OFFSET sig_enter,OFFSET sig_exit\n'
    imports = set(pointers) - {'boom_provider_signal_native_pool'}
    imports.add('boom_java_vm_properties_pool')
    return out, imports


def exports(methods):
    return {'boom_provider_signal_pool', 'boom_provider_signal_service', 'boom_provider_signal_native_pool',
        'boom_provider_signal_open', 'boom_provider_signal_close', 'boom_provider_signal_roots',
        'boom_provider_signal_root_count', 'boom_provider_signal_failure'} | {
        f"boom_m{m['method']}{s}" for m in methods for s in ('', '_native')}
