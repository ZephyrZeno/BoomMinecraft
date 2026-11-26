"""Source contract for the three original static Reference queue natives."""
OWNER = 'java/lang/ref/Reference'
POOL = 'boom_provider_reference_pool'
SERVICE = 'boom_provider_reference_service'
SPECS = [('getAndClearReferencePendingList', '()Ljava/lang/ref/Reference;'),
         ('hasReferencePendingList', '()Z'), ('waitForReferencePendingList', '()V')]
CONTROL = {'boom_provider_reference_' + name for name in ('open', 'stop', 'close', 'boundary')}
FOREIGN = {'TlsAlloc', 'TlsFree', 'TlsGetValue', 'TlsSetValue', 'GetLastError'}
PROCEDURES = FOREIGN | {'boom_reference_pending_' + name for name in ('create', 'get', 'has', 'wait',
                                                                      'stop', 'stopping', 'destroy')} | {'boom_monitor_abort_owned'}
KERNELS = ['reference_pending.asm', 'monitor_abort.asm', 'monitors.asm', 'heap.asm', 'classes32.asm', 'frames.asm']
POLICY = dict(original_ReferenceHandler_loop=True, real_pending_list_wait=True, wait_consumes_pending_head=False,
              cancellation_bound_to_OS_thread_and_Context=True, Java_run_success_on_VM_stop=False,
              owner_must_join_before_close=True, automatic_reference_discovery=False)


def index(summary, classes, S):
    owners = [c for c in classes if c['name'] == OWNER and c['origin']['loader'] == 'bootstrap']
    S.check(len(owners) == 1, 'Original bootstrap Reference is missing or ambiguous')
    owner = owners[0]
    origin = owner['origin']
    S.check(owner['access'] == 0x421 and origin['source_id'] == 'jdk:java.base' and not origin.get('generated'),
            'Reference has a different source or class access')
    R = S.module('pending_reference_class_reader', 'verify-batch-frames.py')
    name, raw = R.original_methods(S.original_class(summary, owner))
    S.check(name == OWNER and len(raw) == len(owner['method_ids']), 'Original Reference method inventory differs')
    methods = []
    for op, (name, descriptor) in enumerate(SPECS):
        found = [(i, m) for i, m in zip(owner['method_ids'], raw) if
                 (m['name'], m['descriptor']) == (name, descriptor)]
        S.check(len(found) == 1 and found[0][1]['access'] == 0x10a and found[0][1]['code'] is None,
                'Reference queue service is not the original private static native')
        methods.append(dict(method=found[0][0], class_id=owner['id'], class_sha256=origin['sha256'], loader='bootstrap',
                            source_id='jdk:java.base', owner=OWNER, name=name, descriptor=descriptor, access=0x10a, operation=op))
    return dict(schema=1, owner=owner['id'], methods=methods, required_classes=[owner['id']], pool_bytes=80, pool_abi=1,
                source_transform_chain='original_locked_no_transforms')


def data(meta=None):
    return (f'.data\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 043525052h,1,0,-1\n'
            ' QWORD OFFSET boom_heap_ptr,0,0,0,0,0,0\n DWORD 0,0\n')


def native_imports(meta):
    return PROCEDURES | {'boom_trace_enter', 'boom_trace_leave'}, (
        {'boom_heap_ptr', 'boom_trace_pool'} | {f"boom_trace_method{m['method']}" for m in meta['methods']})


