"""Independent source/normal-object/pool/MASM/COFF property contract verifier."""
import json
from pathlib import Path, PureWindowsPath
import tomllib
import zipfile


OWNER = 'jdk/internal/util/SystemProps$Raw'
FALLBACKS = ['', 'unknown', 'C:\\', 'en', 'US', 'no', 'NO', 'NY', 'UTF-8', 'GBK',
             'GB18030', 'MS950_HKSCS_XP', 'Windows NT (unknown)', 'Windows 8',
             'Windows 8.1', 'Windows 10', 'Windows 11', 'Windows Server 2012',
             'Windows Server 2012 R2', 'Windows Server 2016', 'Windows Server 2019',
             'Windows Server 2022', 'Windows Server 2025']
DATA_EXPORTS = {'boom_java_properties_roots', 'boom_java_properties_root_count',
                'boom_java_platform_properties_pool', 'boom_java_vm_properties_pool',
                'boom_java_properties_string_pool'}


def check(value, message):
    if not value:
        raise ValueError(message)


def units(text):
    raw = text.encode('utf-16-le', errors='surrogatepass')
    return tuple(int.from_bytes(raw[i:i+2], 'little') for i in range(0, len(raw), 2))


def query(name):
    literals = dict(file_separator='\\', line_separator='\r\n', path_separator=';', os_arch='amd64',
                    sun_cpu_endian='little', sun_io_unicode_encoding='UnicodeLittle', sun_arch_data_model='64')
    key = name.removeprefix('_').removesuffix('_NDX')
    if key in literals:
        return 1, 0, literals[key]
    if key == 'sun_cpu_isalist':
        return 12, 0, 'amd64'
    simple = {'user_dir': 2, 'java_io_tmpdir': 3, 'user_name': 4, 'user_home': 5,
              'os_name': 6, 'os_version': 7, 'sun_os_patch_level': 11,
              'file_encoding': 9, 'sun_jnu_encoding': 9}
    if key in simple:
        return simple[key], 0, None
    if key in ('stdout_encoding', 'stderr_encoding'):
        return 10, int(key == 'stderr_encoding'), None
    locale = [f'{kind}_{part}' for kind in ('display', 'format') for part in ('country', 'language', 'script', 'variant')]
    if key in locale:
        return 8, locale.index(key), None
    null = {f'{p}_{v}' for p in ('ftp', 'http', 'https') for v in ('nonProxyHosts', 'proxyHost', 'proxyPort')}
    null.remove('https_nonProxyHosts')
    null.update(('socksNonProxyHosts', 'socksProxyHost', 'socksProxyPort', 'sun_arch_abi'))
    if key in null:
        return 0, 0, None
    raise ValueError('Unknown original Raw platform property: ' + name)


def source_contract(classes, inventory, static_inputs):
    owners = [c for c in classes if (c['origin']['loader'], c['name']) == ('bootstrap', OWNER)]
    check(len(owners) == 1, 'Missing/ambiguous original Raw')
    cls = owners[0]
    check(cls['origin']['source_id'] == 'jdk:java.base' and cls['origin'].get('generated') is None,
          'Raw source origin differs')
    original = static_inputs[cls['id']]
    check(not original['initializers'] and original['source_sha256'] == cls['origin']['sha256'],
          'Raw source initialization/SHA differs')
    indices = {}
    for f in original['fields']:
        if f['name'] == 'FIXED_LENGTH' or f['name'].endswith('_NDX'):
            check(f['access'] == 0x1a and f['descriptor'] == 'I' and f['constant_value'] is not None,
                  'Raw source index field differs')
            value = original['constants'][str(f['constant_value'])]
            check(set(value) == {'Int'} and 0 <= value['Int'] <= 39, 'Raw source index is not an in-range integer')
            indices[f['name']] = value['Int']
    check(indices.pop('FIXED_LENGTH', None) == 39 and len(indices) == 39 and sorted(indices.values()) == list(range(39)),
          'Raw original indexed schema differs')
    methods = []
    for op, name in enumerate(('platformProperties', 'vmProperties')):
        ids = [i for i in cls['method_ids'] if inventory[i][1:3] == (name, '()[Ljava/lang/String;')]
        check(len(ids) == 1 and inventory[ids[0]][8] == 0x10a and inventory[ids[0]][4] is None,
              'Raw original native signature/access/Code differs')
        methods.append(dict(method=ids[0], class_id=cls['id'], class_sha256=cls['origin']['sha256'],
                            name=name, descriptor='()[Ljava/lang/String;', access=0x10a, operation=op, assembly_unit=0))
    return cls, indices, methods


def vm_values(profile, root):
    check(set(profile) == {'schema', 'java_home', 'class_path', 'library_path', 'properties'} and
          profile['schema'] == 1 and profile['properties'] == [], 'Batch default VM profile differs')
    check(Path(profile['java_home']).absolute() == Path(root).absolute() and PureWindowsPath(profile['java_home']).is_absolute(),
          'VM java.home differs from the declared image output')
    version = tomllib.loads((Path(__file__).resolve().parents[1] / 'Cargo.toml').read_text(encoding='utf-8'))['package']['version']
    values = {'java.home': profile['java_home'], 'java.class.path': profile['class_path'],
              'java.library.path': profile['library_path'], 'sun.boot.library.path': profile['library_path'],
              'java.class.version': '65.0', 'java.vm.name': 'BoomMinecraft Assembly VM',
              'java.vm.vendor': 'BoomMinecraft', 'java.vm.version': version, 'java.vm.info': 'ahead-of-time assembly',
              'java.vm.specification.name': 'Java Virtual Machine Specification',
              'java.vm.specification.vendor': 'Oracle Corporation', 'java.vm.specification.version': '21',
              'jdk.debug': 'release'}
    check(all('\0' not in s and len(units(s)) <= 65535 for pair in values.items() for s in pair), 'Invalid VM profile text')
    return dict(sorted(values.items()))


def model(indices, values):
    texts = set(map(units, FALLBACKS))
    policy = {name: query(name) for name in indices}
    texts.update(units(t) for _, _, t in policy.values() if t is not None)
    texts.update(units(t) for pair in values.items() for t in pair)
    lookup = {t: i for i, t in enumerate(sorted(texts))}
    canonical = []
    for t, i in lookup.items():
        h = 0
        for u in t:
            h = (31*h + u) & 0xffffffff
        canonical.append(dict(id=i, utf16=list(t), java_hash=h))
    rows = [dict(name=name, index=index, query=policy[name][0],
                 argument=lookup[units(policy[name][2])] if policy[name][2] is not None else policy[name][1])
            for name, index in sorted(indices.items(), key=lambda kv: kv[1])]
    pairs = [dict(name=k, key_literal=lookup[units(k)], value_literal=lookup[units(v)]) for k, v in values.items()]
    fallbacks = [lookup[units(t)] for t in FALLBACKS]
    return rows, pairs, canonical, fallbacks


def body(method, cls, op):
    pool, service = (('boom_java_platform_properties_pool', 'boom_platform_properties') if op == 0 else
                     ('boom_java_vm_properties_pool', 'boom_vm_properties'))
    return f'''.code
boom_m{method} PROC FRAME
 sub rsp,56
 .allocstack 56
 .endprolog
 mov QWORD PTR [rsp+32],rcx
 mov QWORD PTR [rsp+40],rdx
 test rcx,rcx
 jz boom_m{method}_zero
 cmp DWORD PTR [rcx],0
 jne boom_m{method}_zero
 lea rcx,boom_class{cls}
 mov rdx,QWORD PTR [rsp+32]
 call boom_class_ensure32
 test eax,eax
 jnz boom_m{method}_zero
 mov rcx,QWORD PTR [rsp+32]
 mov rdx,QWORD PTR [rsp+40]
 call boom_m{method}_native
 add rsp,56
 ret
boom_m{method}_zero:
 xor eax,eax
 add rsp,56
 ret
boom_m{method} ENDP
boom_m{method}_native PROC
 test rcx,rcx
 jz boom_m{method}_raw_zero
 cmp DWORD PTR [rcx],0
 jne boom_m{method}_raw_zero
 lea r8,{pool}
 jmp {service}
boom_m{method}_raw_zero:
 xor eax,eax
 ret
boom_m{method}_native ENDP
'''


def data(shape, array, rows, pairs, texts, fallbacks):
    n = len(texts)
    out = f'.data?\nALIGN 8\nPUBLIC boom_java_properties_roots\nboom_java_properties_roots QWORD ?\nproperty_java_string_roots QWORD {n*2} DUP(?)\nproperty_java_string_states DWORD {n} DUP(?)\n.const\nPUBLIC boom_java_properties_root_count\nboom_java_properties_root_count QWORD {n*2+1}\nproperty_java_platform_rows LABEL DWORD\n'
    out += ''.join(f" DWORD {r['index']},{r['query']},{r['argument']},0\n" for r in rows)
    out += 'property_java_fallbacks LABEL DWORD\n' + ''.join(f' DWORD {i}\n' for i in fallbacks)
    out += 'property_java_vm_rows LABEL DWORD\n' + ''.join(f" DWORD {r['key_literal']},{r['value_literal']}\n" for r in pairs)
    out += 'ALIGN 8\nproperty_java_string_entries LABEL BYTE\n'
    for t in texts:
        out += f" QWORD OFFSET property_java_text_{t['id']}\n DWORD {len(t['utf16'])},0{t['java_hash']:08X}h\n"
    for t in texts:
        out += f"ALIGN 2\nproperty_java_text_{t['id']} LABEL WORD\n"
        if not t['utf16']:
            out += ' WORD 0\n'
        for i in range(0, len(t['utf16']), 16):
            out += ' WORD ' + ','.join(f'0{u:04X}h' for u in t['utf16'][i:i+16]) + '\n'
    callbacks = ' QWORD OFFSET boom_java_property_array,OFFSET boom_java_property_copy,OFFSET boom_java_property_literal,OFFSET boom_java_string_literal\n'
    out += f'.data\nALIGN 8\nPUBLIC boom_java_platform_properties_pool\nboom_java_platform_properties_pool DWORD 050524F50h,2,0,0\n QWORD OFFSET boom_heap_ptr,OFFSET property_java_string_pool,OFFSET boom_t{array},OFFSET boom_java_properties_roots,OFFSET property_java_platform_rows\n DWORD {len(rows)},0\n QWORD OFFSET property_java_fallbacks,0\n' + callbacks
    out += f'PUBLIC boom_java_vm_properties_pool\nboom_java_vm_properties_pool DWORD 0564D5052h,2,{len(pairs)},0\n QWORD OFFSET boom_heap_ptr,OFFSET property_java_string_pool,OFFSET boom_t{array},OFFSET property_java_vm_rows,0,0,0,0\n' + callbacks
    out += f"PUBLIC boom_java_properties_string_pool\nboom_java_properties_string_pool LABEL BYTE\nproperty_java_string_pool DWORD 04A534C50h,1,{n},1\n QWORD OFFSET property_java_string_entries,OFFSET property_java_string_roots,OFFSET property_java_string_states,OFFSET boom_layout{shape['class_id']}\n DWORD {shape['value_offset']},{shape['coder_offset']},{shape['hash_offset']},{shape['hash_is_zero_offset']}\n QWORD 0\n DWORD 0,0\n"
    return out


def verify(root, batch, plan, inventory, static_inputs, available, artifact, coff_symbols, file_digest,
           expected_image_home=None):
    root, plan = Path(root), Path(plan)
    s, shape = batch['properties'], batch['string_literals']['source_layout']
    check((s['abi'], s['context_bytes'], s['pool_abi'], s['native_methods'], s['platform_properties']) == (1, 32, 2, 2, 39),
          'Invalid normal property ABI')
    check(all(s[k] is False for k in ('raw_class_initialization_executed', 'original_raw_constructor_executed',
          'full_system_initialization_executed', 'automatic_gc', 'linked')), 'Properties falsely claim execution/bootstrap/GC')
    classes = list(map(json.loads, (plan / 'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    cls, indices, methods = source_contract(classes, inventory, static_inputs)
    check((s['class_id'], s['class_sha256']) == (cls['id'], cls['origin']['sha256']), 'Properties owner identity differs')
    with zipfile.ZipFile(artifact(root, batch['runtime_metadata']['index'], 'runtime-metadata')) as z:
        arrays = [t for t in map(json.loads, z.read('types.jsonl').splitlines()) if
                  (t['defining_loader'], t['name']) == ('bootstrap', '[Ljava/lang/String;')]
    check(len(arrays) == 1 and arrays[0]['kind'] == 3 and arrays[0]['parent_component'] == shape['class_id'] and
          arrays[0]['id'] == s['array_type'], 'Properties must use the normal source String[] descriptor')
    # The normal batch owns its VM home. A verified sparse artifact resolver can
    # retain the source batch's declared original VM home and Properties COFF.
    if expected_image_home is None:
        expected_image_home = getattr(artifact,'verified_original_vm_image_home',root)
    rows, pairs, texts, fallbacks = model(indices, vm_values(s['vm_profile'], expected_image_home))
    check((s['canonical_strings'], s['root_cells'], s['vm_pairs']) == (len(texts), 2*len(texts)+1, len(pairs)),
          'Properties canonical/root/profile count differs')
    with zipfile.ZipFile(artifact(root, s['index'], 'properties')) as z:
        expected = [('methods.jsonl', methods), ('platform.jsonl', rows), ('vm.jsonl', pairs), ('strings.jsonl', texts)]
        check(z.namelist() == [k for k, _ in expected] + ['fallbacks.json'], 'Properties index coverage differs')
        for name, value in expected:
            check(list(map(json.loads, z.read(name).splitlines())) == value, 'Properties index differs: ' + name)
        check(json.loads(z.read('fallbacks.json')) == fallbacks, 'Properties fallback policy differs')
    check(len(s['units']) == 1, 'Unexpected property unit count')
    u = s['units'][0]
    text = artifact(root, u['assembly'], 'properties').read_text(encoding='utf-8')
    expected_body = data(shape, s['array_type'], rows, pairs, texts, fallbacks) + ''.join(body(m['method'], cls['id'], m['operation']) for m in methods)
    check(text.partition('.code\n')[2][:-5] == expected_body and text.endswith('\nEND\n'), 'Properties MASM differs from source model')
    check(u['object'] is not None and u['assembler_diagnostic'] is None, 'Properties actual assembly failed')
    defined, undefined = coff_symbols(artifact(root, u['object'], 'properties'))
    required = DATA_EXPORTS | {f"boom_m{m['method']}{suffix}" for m in methods for suffix in ('', '_native')}
    source = {'boom_heap_ptr', f"boom_layout{shape['class_id']}", f"boom_t{s['array_type']}", f"boom_class{cls['id']}", 'boom_java_string_literal'}
    runtime = {'boom_class_ensure32', 'boom_java_property_array', 'boom_java_property_copy', 'boom_java_property_literal',
               'boom_platform_properties', 'boom_vm_properties'}
    check(defined == required and source <= available and undefined == source | runtime, 'Properties COFF definitions/imports differ')
    check(set(s['kernel_sha256']) == {'native/runtime/system_properties.asm', 'native/runtime/vm_properties.asm', 'native/runtime/java_properties.asm'},
          'Properties kernel coverage differs')
    for path, digest in s['kernel_sha256'].items():
        check(file_digest(Path(__file__).resolve().parents[1] / path)['sha256'] == digest, 'Properties MASM kernel changed')
    return dict(verified=True, scope='source_native_indices_declared_VM_config_normal_objects_MASM_COFF_only',
                native_methods=2, platform_properties=39, vm_pairs=len(pairs), execution_verified=False, game_started=False), defined, undefined, {m['method'] for m in methods}
