"""Compare the standalone Win64 assembly metadata kernel with the locked Windows JDK."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import ctypes as c
import hashlib
import importlib.util
import json
import msvcrt
import os
from pathlib import Path
import socket
import struct
import subprocess
from tempfile import TemporaryDirectory
from threading import Barrier, get_native_id
from uuid import uuid4
import winreg
import _winapi


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / '.boom'
KERNEL = ROOT / 'native/runtime/win32_path_attributes.asm'
ORACLE = ROOT / 'java/reference/WindowsPathAttributesReference.java'
P, U, Q = c.c_void_p, c.c_uint32, c.c_uint64
EPOCH_TICKS = 116444736000000000


def check(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked(record, local=True):
    path = Path(record['path']).resolve(strict=True)
    check(not local or path.is_relative_to(ART), 'Expected source record in project .boom')
    check(path.stat().st_size == record['digest']['size'] and sha(path) == record['digest']['sha256'],
          f'Locked source digest differs for {path}')
    return path


def bind(dll, name, result, *args):
    proc = getattr(dll, name)
    proc.restype, proc.argtypes = result, args
    return proc


def run(cmd, directory):
    result = subprocess.run(cmd, cwd=directory, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'{cmd[0]} exited {result.returncode}\n' +
                           (result.stdout + result.stderr).decode('utf-8', errors='replace'))
    return result.stdout


def source_records(config):
    batch, plan = (Path(config[k]).resolve(strict=True) for k in ('batch', 'plan'))
    check(batch.is_relative_to(ART) and plan.is_relative_to(ART), 'Input batch/plan outside project')
    summary = read(batch / 'summary.json')
    check(read(batch / 'verification.json')['verified'], 'Source batch verification is missing')
    prepared = read(plan / 'summary.json')
    check(prepared['input_fingerprint'] == summary['input_fingerprint'] and prepared['game_version'] == '1.21.1',
          'Expected matching 1.21.1 source batch/plan')
    catalog = checked(summary['frames']['original_system_catalog'])
    module_image = checked(read(catalog)['image'], local=False)
    spec = importlib.util.spec_from_file_location('path_attributes_class_reader', ROOT / 'scripts/verify-batch-frames.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    requests = {
        'sun/nio/fs/WindowsFileAttributes': {
            'get': ('(Lsun/nio/fs/WindowsPath;Z)Lsun/nio/fs/WindowsFileAttributes;', 8),
            **{n: ('()Z', 1) for n in ('isRegularFile', 'isOther', 'isDirectory', 'isSymbolicLink')}},
        'sun/nio/fs/WindowsNativeDispatcher': {'GetFileAttributesEx0': ('(JJ)V', 0x10a),
            'GetFileInformationByHandle0': ('(JJ)V', 0x10a), 'DeviceIoControlGetReparsePoint': ('(JJI)V', 0x108)},
        'java/io/WinNTFileSystem': {n: ('(Ljava/io/File;)J', 0x102) for n in ('getLength0', 'getLastModifiedTime0')},
        'jdk/internal/module/SystemModuleFinders': {'ofSystem': ('()Ljava/lang/module/ModuleFinder;', 9)}}
    records = {}
    with checked(prepared['artifacts']['classes']).open(encoding='utf8') as stream:
        for line in stream:
            src = json.loads(line)
            name, origin = src['name'], src['origin']
            if name not in requests or origin['loader'] != 'bootstrap':
                continue
            check(origin['source_id'] == 'jdk:java.base' and not origin.get('generated'), 'Expected original java.base class')
            root = (catalog.parent / 'image').resolve()
            file = (root / origin['jar_entry']).resolve(strict=True)
            check(file.is_relative_to(root) and sha(file) == origin['sha256'], 'Original class digest differs')
            declared, methods = reader.original_methods(file.read_bytes())
            check(declared == name and len(methods) == len(src['method_ids']), 'Original class inventory differs')
            matched = {}
            for ident, method in zip(src['method_ids'], methods):
                member = method['name']
                if requests[name].get(member) != (method['descriptor'], method['access']):
                    continue
                check(member not in matched and (method['code'] is None) == bool(method['access'] & 0x100),
                      'Original native/Java code declaration differs')
                matched[member] = ident
            check(set(matched) == set(requests[name]), f'Missing methods in the locked {name}')
            records[name] = dict(class_id=src['id'], sha256=origin['sha256'], methods=matched)
    check(set(records) == set(requests), 'Missing original module/filesystem sources')
    return module_image, records


def build(out):
    locator = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    install = Path(run([locator, '-utf8', '-latest', '-products', '*', '-requires',
                        'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], out)
                   .decode('utf-8-sig').strip())
    version = (install / 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt').read_text().strip()
    tools = install / f'VC/Tools/MSVC/{version}/bin/Hostx64/x64'
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
        sdk = Path(winreg.QueryValueEx(key, 'KitsRoot10')[0])
    libs = sorted((sdk / 'Lib').glob('*/um/x64/kernel32.lib'),
                  key=lambda p: tuple(int(s) for s in p.parents[2].name.split('.')))
    obj, dll = out / 'attributes.obj', out / 'attributes.dll'
    run([tools / 'ml64.exe', '/nologo', '/c', f'/Fo{obj}', KERNEL], out)
    linker = [tools / 'link.exe', '/nologo', '/dll', '/noentry', '/nodefaultlib', '/machine:x64',
              '/dynamicbase', '/nxcompat', '/brepro', '/export:boom_win32_path_attributes']
    run([*linker, f'/out:{dll}', obj, libs[-1]], out)
    imports = run([tools / 'dumpbin.exe', '/nologo', '/imports', dll], out).decode('ascii', errors='replace')
    dependencies = {line.strip().lower() for line in imports.splitlines() if line.strip().lower().endswith('.dll')}
    dependencies.discard(('Dump of file ' + str(dll)).lower())
    check(dependencies == {'kernel32.dll'}, 'Unexpected non-Windows runtime import')
    for name in ('GetFileAttributesExW', 'GetFileInformationByHandle', 'DeviceIoControl', 'CreateFileW',
                 'CloseHandle', 'GetLastError', 'FindFirstFileW', 'FindClose', 'LocalAlloc', 'LocalFree'):
        check(name in imports, 'Missing Win32 import ' + name)
    # NTFS on many hosts completes attribute-only queries even when a process
    # opened the file with zero share access. Force only the *first* Win32
    # API to report ERROR_SHARING_VIOLATION in a separate test DLL. The
    # original kernel object still opens/finds/closes the real directory entry.
    shim = out / 'sharing-test.asm'
    shim.write_text('''option casemap:none
EXTERN SetLastError:PROC
.code
GetFileAttributesExW PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 mov ecx,32
 call SetLastError
 xor eax,eax
 add rsp,40
 ret
GetFileAttributesExW ENDP
END
''', encoding='ascii')
    fixture = out / 'sharing-test.obj'
    run([tools / 'ml64.exe', '/nologo', '/c', f'/Fo{fixture}', shim], out)
    sharing_dll = out / 'sharing-test.dll'
    run([*linker, f'/out:{sharing_dll}', obj, fixture, libs[-1]], out)
    return dll, sharing_dll


def extended(path):
    text = str(path)
    if len(text.encode('utf-16-le')) < 496 or text.startswith('\\\\?\\'):
        return text
    return '\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text


def fixture_paths(directory, module_image, windows, held):
    file = directory / 'résumé 游戏 🎮.dat'
    file.write_bytes(b'original-file-metadata')
    old_ns = -1234567890000000
    os.utime(file, ns=(old_ns, old_ns))
    empty = directory / 'empty'
    empty.touch()
    hidden = directory / 'hidden'
    hidden.write_bytes(b'hidden')
    set_attrs = bind(windows, 'SetFileAttributesW', c.c_int, c.c_wchar_p, U)
    check(set_attrs(str(hidden), 2), 'Cannot create hidden-file fixture')
    subdir = directory / 'target'
    subdir.mkdir()
    long_dir = subdir
    while len(str(long_dir)) < 278:
        long_dir = long_dir / ('long-path-' + 'x' * 44)
        os.mkdir(extended(long_dir))
        held.callback(os.rmdir, extended(long_dir))
    long_file = long_dir / '末尾.txt'
    with open(extended(long_file), 'wb') as f:
        f.write(b'long')
    held.callback(os.unlink, extended(long_file))
    sparse = directory / 'sparse.bin'
    device = bind(windows, 'DeviceIoControl', c.c_int, P, U, P, U, P, U, c.POINTER(U), P)
    with sparse.open('xb') as f:
        returned = U()
        check(device(msvcrt.get_osfhandle(f.fileno()), 0x900c4, None, 0, None, 0, c.byref(returned), None),
              'FSCTL_SET_SPARSE failed before the large-file fixture')
        f.seek((1 << 32) + 17)
        f.write(b'x')
    alias = directory / 'junction'
    _winapi.CreateJunction(str(subdir), str(alias))
    hard = directory / 'hardlink'
    os.link(file, hard)
    locked = directory / 'exclusive'
    locked.write_bytes(b'opened without sharing')
    create = bind(windows, 'CreateFileW', P, c.c_wchar_p, U, U, P, U, U, P)
    handle = create(str(locked), 0x80000000, 0, None, 3, 0x80, None)
    check(handle not in (None, P(-1).value), 'Could not create exclusive-share fixture')
    held.callback(bind(windows, 'CloseHandle', c.c_int, P), handle)
    paths = dict(module_image=module_image, unicode_file=file, directory=subdir, empty_file=empty,
                 missing=directory / 'missing', missing_parent=directory / 'absent' / 'x', hidden=hidden,
                 sparse_over_4GiB=sparse, long_path=long_file, junction=alias, hardlink=hard, exclusive=locked)
    optional = {}
    try:
        first = directory / 'symlink'
        first.symlink_to(file)
    except OSError as exc:
        if exc.winerror != 1314:
            raise
        optional['symbolic_links'] = 'CreateSymbolicLinkW needs a privilege on this host (1314)'
    else:
        paths['symlink'] = first
        paths['directory_link'] = directory / 'directory-link'
        paths['directory_link'].symlink_to(subdir, target_is_directory=True)
        paths['dangling_link'] = directory / 'dangling'
        paths['dangling_link'].symlink_to(directory / 'missing')
    # CPython on Windows can create AF_UNIX sockets by number. Its public
    # socket.bind only decodes Internet-family addresses on several releases.
    ws = c.WinDLL('ws2_32')
    try:
        sock = held.enter_context(socket.socket(1, socket.SOCK_STREAM))
    except OSError as exc:
        if exc.winerror != 10047:
            raise
        optional['AF_UNIX'] = 'WSAEAFNOSUPPORT'
    else:
        unix = directory / 'socket'
        encoded = os.path.relpath(unix).encode('utf-8')
        check(len(encoded) < 108, 'Unix socket fixture exceeds sockaddr_un.sun_path')
        sockaddr = struct.pack('<H108s', 1, encoded)
        status = bind(ws, 'bind', c.c_int, c.c_size_t, c.c_char_p, c.c_int)(sock.fileno(), sockaddr, len(sockaddr))
        check(status == 0, f'Could not bind local filesystem socket, WSA result {ws.WSAGetLastError()}')
        paths['local_socket'] = unix
    return paths, optional


def oracle(java, out, paths, accurate):
    # Some Windows java.exe launchers narrow CLI arguments to the local ANSI
    # code page, so pass Unicode path names through an explicit UTF-8 file.
    names_file = out / 'oracle-paths.txt'
    names_file.write_text('\n'.join(map(str, paths.values())) + '\n', encoding='utf-8')
    data = run([java, '-Xmx96m', '--add-opens=java.base/sun.nio.fs=ALL-UNNAMED',
                '-Dsun.nio.fs.ensureAccurateMetadata=' + str(bool(accurate)).lower(), '-cp', out,
                'WindowsPathAttributesReference', names_file.name], out).decode('ascii')
    values = {}
    names = list(paths)
    for line in data.splitlines():
        idx, follow, regular, status, *rest = line.split()
        key = names[int(idx)], int(follow) | (2 * accurate)
        check(key not in values and regular in ('true', 'false'), 'Malformed JVM result')
        if status == 'ERROR':
            check(len(rest) == 1 and regular == 'false', 'JVM failure or regular-file predicate differs')
            values[key] = rest[0]
        else:
            fields = tuple(map(int, rest))
            check(status == 'OK' and len(fields) == 7 and (regular == 'true') == bool(fields[-1] & 1),
                  'Files.isRegularFile disagrees with the JDK attribute snapshot')
            values[key] = fields
    check(len(values) == 2 * len(paths), 'JVM oracle missed paths')
    return values


def query(proc, path, flags):
    guard = (c.c_ubyte * 64)(*([0xa5] * 64))
    status = proc(extended(path) if path is not None else None, flags, c.byref(guard, 8))
    raw = bytes(guard)
    check(raw[:8] == raw[-8:] == b'\xa5' * 8 and (not status or raw[8:56] == b'\xa5' * 48),
          'Native metadata overwrote a guard or published a partial failure')
    if status:
        return status, None
    attrs, tag, creation, access, write, size, kinds, reserved = struct.unpack_from('<IIQQQQII', raw, 8)
    check(reserved == 0, 'Result reserved field is nonzero')
    return 0, (attrs, tag, creation, access, write, size, kinds)


def compare(proc, path, flags, expected, label):
    error, value = query(proc, path, flags)
    if isinstance(expected, str):
        check(error and value is None, f'{label} should have raised {expected}')
        if expected == 'NoSuchFileException':
            check(error in (2, 3), f'{label} expected file/path not found, got {error}')
        elif expected == 'AccessDeniedException':
            check(error == 5, f'{label} expected access denied, got {error}')
        return error
    # The same module image is also being read by our oracle JVM. Its access
    # time can advance between snapshots. All other fields still compare.
    observed, wanted = list(value or ()), list(expected)
    if label == 'module_image' and value:
        observed[3] = wanted[3]
    check(not error and observed == wanted,
          f'{label} flags={flags} error={error} differs from JVM: {value!r} vs {expected!r}')
    return 0


def exercise(dll, sharing_dll, module_image, out):
    windows = c.WinDLL('kernel32', use_last_error=True)
    proc = bind(c.CDLL(str(dll)), 'boom_win32_path_attributes', U, c.c_wchar_p, U, P)
    forced_sharing = bind(c.CDLL(str(sharing_dll)), 'boom_win32_path_attributes', U, c.c_wchar_p, U, P)
    java = module_image.parents[1] / 'bin/java.exe'
    run([java.with_name('javac.exe'), '-encoding', 'UTF-8', '-d', out, ORACLE], out)
    with TemporaryDirectory(dir=out, prefix='files-') as temp, ExitStack() as held:
        directory = Path(temp).resolve()
        check(directory.parent == out and directory.is_relative_to(ART), 'Fixture directory escaped test output')
        paths, optional = fixture_paths(directory, module_image, windows, held)
        expected = {**oracle(java, out, paths, 0), **oracle(java, out, paths, 1)}
        errors = {}
        for (name, flags), value in expected.items():
            errors[name, flags] = compare(proc, paths[name], flags, value, name)
        check(query(proc, None, 0)[0] == query(proc, paths['unicode_file'], 4)[0] == 87 and
              proc(str(paths['unicode_file']), 0, None) == 87, 'Invalid native argument accepted')
        check(expected['module_image', 1][-1] == 1 and expected['module_image', 1][5] == module_image.stat().st_size and
              expected['sparse_over_4GiB', 1][5] == (1 << 32) + 18 and
              expected['unicode_file', 1][4] == EPOCH_TICKS - 12345678900000 and
              expected['hidden', 1][0] & 2 and expected['junction', 0][1] == 0xa0000003 and
              expected['junction', 0][-1] == 10 and expected['junction', 1][-1] == 2,
              'Missing fixture coverage for file type, reparse policy, time or 64-bit length')
        if 'local_socket' in paths:
            check(all(expected['local_socket', f][1] == 0x80000023 and expected['local_socket', f][-1] == 8
                      for f in range(4)), 'AF_UNIX follow/nofollow classification differs')
        if 'symlink' in paths:
            check(expected['symlink', 0][-1] == 4 and expected['symlink', 1][-1] == 1 and
                  expected['dangling_link', 0][-1] == 4 and errors['dangling_link', 1],
                  'Missing file link or dangling link coverage')
        for name in ('unicode_file', 'directory', 'sparse_over_4GiB', 'long_path'):
            compare(forced_sharing, paths[name], 1, expected[name, 1], name)
        for name in ('junction', 'missing', 'missing_parent'):
            check(query(forced_sharing, paths[name], 1)[0] == 32, 'FindFirstFile failure lost the first error')
        check(query(forced_sharing, str(paths['directory']) + '\\', 1)[0] == 32 and
              query(forced_sharing, paths['directory'].drive, 1)[0] == 32, 'Sharing fallback accepted a root suffix')
        cases = [(name, f) for name in paths if name != 'module_image' for f in range(4)]
        gate = Barrier(8, timeout=15)
        def worker(offset):
            gate.wait()
            for i in range(100):
                name, flag = cases[(i + offset) % len(cases)]
                compare(proc, paths[name], flag, expected[name, flag], name)
            return get_native_id()
        with ThreadPoolExecutor(8) as workers:
            threads = set(workers.map(worker, range(8)))
        check(len(threads) == 8, 'Did not exercise eight simultaneous Windows threads')
        handles = bind(windows, 'GetProcessHandleCount', c.c_int, P, c.POINTER(U))
        current = bind(windows, 'GetCurrentProcess', P)()
        before, after = U(), U()
        check(handles(current, c.byref(before)), 'Cannot sample Windows handle count')
        for _ in range(16):
            for name, flag in cases:
                compare(proc, paths[name], flag, expected[name, flag], name)
        check(handles(current, c.byref(after)) and after.value == before.value, 'Filesystem query leaked a Windows handle')
        return dict(fixtures=list(paths), optional_unavailable=optional, JVM_comparisons=len(expected),
                    parallel_OS_threads=len(threads), parallel_assembly_calls=800,
                    stable_handle_checks=16 * len(cases), handles_before=before.value, handles_after=after.value,
                    source_module_image=str(module_image), module_image_size=module_image.stat().st_size,
                    regular_file_fast_and_handle=True, sparse_file_size=(1 << 32) + 18,
                    junction_no_follow_kind=expected['junction', 0][-1], junction_follow_kind=expected['junction', 1][-1],
                    exclusive_handle_Win32_errors=[errors['exclusive', f] for f in range(4)],
                    controlled_sharing_fallback_cases=9, controlled_first_API='GetFileAttributesExW returns 32',
                    fallback_directory_entries_obtained_from_Windows=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ART / 'pending-native-module-descriptors-v140.json')
    args = parser.parse_args()
    check(os.name == 'nt' and c.sizeof(P) == 8, 'Windows x64 required')
    module_image, contracts = source_records(read(args.config))
    out = ART / 'win32-path-attributes-tests' / uuid4().hex
    out.mkdir(parents=True)
    original_sha = sha(KERNEL)
    dll, sharing_dll = build(out)
    report = exercise(dll, sharing_dll, module_image, out)
    check(sha(KERNEL) == original_sha, 'Assembly source changed during execution')
    report.update(passed=True, kernel_sha256=original_sha, kernel_dll_sha256=sha(dll),
                  locked_source_declarations=contracts, artifact_directory=str(out),
                  tested_ABI='normalized Win32 UTF-16 path to native metadata48',
                  selected_Java_or_native_binding_executed=False, game_started=False)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
