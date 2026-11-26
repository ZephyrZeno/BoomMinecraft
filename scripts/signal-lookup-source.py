"""Original Signal declarations and the Windows name lookup contract.

This rule only implements findSignal0. Installing handlers, raising signals and
dispatching Java callbacks require the separate signal/thread runtime.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('signal_original_methods', Path(__file__).with_name('verify-batch-frames.py'))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
OWNER = 'jdk/internal/misc/Signal'
SPECS = (('findSignal0', '(Ljava/lang/String;)I'), ('handle0', '(IJ)J'), ('raise0', '(I)V'))
WINDOWS_SIGNALS = (('ABRT', 22), ('FPE', 8), ('SEGV', 11), ('INT', 2), ('TERM', 15), ('BREAK', 21), ('ILL', 4))
KERNELS = ['classes32.asm', 'heap.asm', 'objects.asm']
REFERENCE = 'https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/os/windows/os_windows.cpp#L5658'


def index(summary, classes, S):
    owners = [c for c in classes if c['name'] == OWNER and c['origin']['loader'] == 'bootstrap']
    S.check(len(owners) == 1, 'Original Signal owner missing or ambiguous')
    owner = owners[0]
    S.check(owner['origin']['source_id'] == 'jdk:java.base' and not owner['origin'].get('generated') and owner['access'] == 0x31,
            'Signal lookup needs its original final bootstrap class')
    name, methods = R.original_methods(S.original_class(summary, owner))
    S.check(name == OWNER and len(methods) == len(owner['method_ids']), 'Original Signal method inventory differs')
    natives = [(i, r) for i, r in zip(owner['method_ids'], methods) if r['access'] & 0x100]
    S.check(len(natives) == len(SPECS), 'Original Signal native inventory differs')
    declarations = []
    for op, (name, descriptor) in enumerate(SPECS):
        found = [(i, r) for i, r in natives if (r['name'], r['descriptor']) == (name, descriptor)]
        S.check(len(found) == 1 and found[0][1]['access'] == 0x10a and found[0][1]['code'] is None,
                'Original Signal native declaration differs: ' + name)
        declarations.append(dict(method=found[0][0], class_id=owner['id'], class_sha256=owner['origin']['sha256'],
            loader='bootstrap', source_id='jdk:java.base', owner=OWNER, name=name, descriptor=descriptor, access=0x10a, operation=op))
    return dict(schema=1, lookup=declarations[0], unavailable_natives=declarations[1:],
                platform='Windows', signals=[dict(name=n, number=i) for n, i in WINDOWS_SIGNALS],
                normal_String_pool_abi=1, normal_String_pool_bytes=80, case_sensitive=True,
                unknown_signal=-1, handler_installation=False, signal_raise=False, Java_signal_dispatch=False,
                source_transform_chain='original_locked_no_transforms', reference=REFERENCE, game_started=False)


def data():
    text = '.const\nALIGN 8\nprovider_signal_lookup_rows LABEL BYTE\n'
    for name, number in WINDOWS_SIGNALS:
        values = list(name.encode('ascii')) + [0] * (8 - len(name))
        text += f' DWORD {len(name)},{number}\n BYTE ' + ','.join(map(str, values)) + '\n'
    return text + ('.data\nALIGN 8\nPUBLIC boom_provider_signal_lookup_pool\n'
        'boom_provider_signal_lookup_pool DWORD 053494750h,1\n'
        ' QWORD OFFSET boom_heap_ptr,OFFSET boom_java_string_literal_pool,0\n')
