"""Original Win32ErrorMode native over the existing assembly Windows API service."""
KERNELS = ['classes32.asm', 'windows_startup.asm']
POLICY = dict(normal_source_layouts=True, platform='Windows', mutates_process_error_mode=True,
              mode_scope='current_native_guest_process', low_UINT_argument=True, unsigned_UINT_return=True)


def contracts(owner, raw, S):
    S.check(owner['name'] == 'sun/io/Win32ErrorMode' and owner['access'] == 0x21 and
        owner['origin']['loader'] == 'bootstrap' and owner['origin']['source_id'] == 'jdk:java.base' and
        not owner['origin'].get('generated') and len(raw) == len(owner['method_ids']),
        'Windows startup requires original bootstrap Win32ErrorMode')
    S.check(not any(m['name'] == '<clinit>' for m in raw), 'Original Win32ErrorMode has no class initializer')
    natives = [(i,m) for i,m in zip(owner['method_ids'],raw) if m['access']&0x100]
    S.check(len(natives) == 1, 'Windows startup original native inventory differs')
    i,m = natives[0]
    S.check((m['name'],m['descriptor'],m['access'],m['code']) == ('setErrorMode','(J)J',0x10a,None),
            'Windows startup private native declaration differs')
    return [dict(method=i,class_id=owner['id'],class_sha256=owner['origin']['sha256'],loader='bootstrap',
        source_id='jdk:java.base',owner=owner['name'],name=m['name'],descriptor=m['descriptor'],access=0x10a,operation=0)]


def index(summary, classes, S):
    R = S.module('windows_startup_original_reader', 'verify-batch-frames.py')
    found = [c for c in classes if (c['origin']['loader'],c['name']) == ('bootstrap','sun/io/Win32ErrorMode')]
    S.check(len(found) == 1, 'Original Windows startup owner missing or ambiguous')
    owner = found[0]
    name,raw = R.original_methods(S.original_class(summary,owner))
    S.check(name == owner['name'], 'Original Windows startup class identity differs')
    return dict(schema=1,methods=contracts(owner,raw,S),pool_bytes=32,pool_abi=1,
        source_transform_chain='original_locked_no_transforms',game_started=False)


def data():
    return ('.const\nALIGN 8\nPUBLIC boom_provider_windows_startup_pool\n'
            'boom_provider_windows_startup_pool DWORD 050535742h,1\n QWORD 0,0,0\n')
