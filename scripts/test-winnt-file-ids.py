"""Check WinNTFileSystem.initIDs in an already verified original-source image on Windows."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import struct
import subprocess
import sys
from threading import Barrier, get_native_id
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
P, U, Q = c.c_void_p, c.c_uint32, c.c_uint64
Context = Q * 4


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def checked(record):
    path = Path(record['path'])
    check(path.stat().st_size == record['digest']['size'] and sha(path) == record['digest']['sha256'],
          'Source artifact changed: ' + str(path))
    return path


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, args
    return fn


def address(dll, name):
    return c.addressof(c.c_byte.in_dll(dll, name))


def word(addr, offset=0):
    return U.from_address(addr + offset).value


def pointer(addr, offset=0):
    return P.from_address(addr + offset).value


def host_held_monitors(heap):
    check(word(heap,104) == 0, 'Host monitor registry is busy')
    node = pointer(heap,96)
    held = []
    while node:
        check(word(node,16) == get_native_id() and word(node,20) > 0 and word(node,24) == 0,
              'Unexpected foreign owner or monitor waiter in isolated setup')
        held.append((pointer(node),word(node,20)))
        node = pointer(node,8)
    check(sum(count for _,count in held) == Q.from_address(heap+112).value, 'Setup monitor count differs')
    return held


def final_path(fn, handle):
    size = fn(handle, None, 0, 0)
    check(1 < size < 65536, 'Windows did not report a path buffer size')
    buf = c.create_unicode_buffer(size)
    check(0 < fn(handle, buf, size, 0) < size, 'Windows could not resolve the open file handle')
    return buf.value


def probe(runtime, selection, out, cold):
    proof = read(selection/'selection-verification.json')
    check(proof['verified'] and proof['closure_manifest_sha256'] == sha(selection/'closure.json'),
          'The selected original-source closure changed')
    closure = read(selection/'closure.json')
    [ref] = [r for r in closure['runtime_provider_packs']
             if read(checked(r['manifest']))['family'] == 'normal-winnt-filesystem-v1']
    provider = read(checked(ref['manifest']))
    checked_pack = read(checked(ref['verification']))
    check(checked_pack['verified'] and checked_pack['provider_manifest_sha256'] == ref['manifest']['digest']['sha256'] and
          str(checked(provider['object'])) in closure['objects'], 'Source provider object or verification changed')
    meta = read(checked(provider['winnt_filesystem_metadata']))
    states = {r['name']:r for r in closure['selected_classes']}
    file, winnt, system = (states[n] for n in ('java/io/File','java/io/WinNTFileSystem','java/lang/System'))
    [member] = meta['methods']
    check((meta['file_class'],meta['file_sha256'],meta['owner'],member['class_sha256']) ==
          (file['class_id'],file['source_sha256'],winnt['class_id'],winnt['source_sha256']) and
          (member['name'],member['descriptor'],member['access']) == ('initIDs','()V',0x10a) and
          (meta['field']['name'],meta['field']['descriptor'],meta['field']['offset'],meta['field']['width']) ==
          ('path','Ljava/lang/String;',0,8), 'Original File.path or WinNTFileSystem.initIDs differs')
    config = read(selection/'vm-thread-bootstrap.json')
    image_path, rt_path = selection/'diagnostic-image.dll', runtime/'boom-runtime.dll'
    check(Path(config['runtime']).resolve() == rt_path and Path(config['image']).resolve() == image_path and
          sha(rt_path) == read(runtime/'runtime.json')['sha256'], 'Runtime or selected image differs')
    with os.add_dll_directory(str(runtime)):
        rt, image = c.CDLL(str(rt_path)), c.CDLL(str(image_path))
    pool = address(image, provider['pool_symbol'])
    service = bind(image, provider['service_symbol'], Q, P, P, P, U)
    native = bind(image, 'boom_m'+str(member['method']), Q, P, P)
    file_class = address(image, 'boom_class'+str(file['class_id']))
    field = pointer(pool, 24)
    check(pointer(pool,16) == file_class and word(pool,8) == 0 and not pointer(pool,32) and not pointer(pool,40) and
          word(field,8) == 0 and word(field,12) == meta['field']['index'] and word(field,16) == file['class_id'] and
          word(field,20) == 8 and word(pointer(field),16) > 0, 'Cold source field record differs')
    heap = bind(rt,'boom_heap_create',P,Q)(128 << 20)
    check(heap and bind(image,'boom_java_string_literals_bind_heap',U,P)(heap) == 1, 'Test heap binding failed')
    try:
        if cold:
            # Without System properties the actual File initializer fails. Repeat
            # against that real failed class to exercise its cached failure state.
            first, second = Context(), Context()
            service(first,None,pool,0)
            check(word(c.addressof(first)) != 0 and word(file_class,8) == 3, 'Cold File initializer did not fail')
            service(second,None,pool,0)
            check(word(c.addressof(second)) == 9 and word(pool,8) == 0 and not pointer(pool,32) and not pointer(pool,40),
                  'Class initialization failure published a field ID or Windows function')
            result = dict(initial_kind=word(c.addressof(first)),method=word(c.addressof(first),8),
                          repeated_kind=word(c.addressof(second)),registration_state=word(pool,8))
        else:
            # This FFI host has no primordial Java thread. Original phase 1
            # publishes System.props before reaching a later VM dependency.
            prep = Context()
            bind(image,config['system_entry_symbol'],Q,P,P)(prep,None)
            setup_monitors = host_held_monitors(heap)
            props = next(f['index'] for f in system['fields'] if f['name']=='props')
            check(pointer(address(image,f"boom_s{system['class_id']}_{props}")) and word(file_class,8) == 0 and
                  word(pool,8) == 0 and not Q.from_address(address(image,'boom_provider_threads_pool')+168).value,
                  'Expected source-published properties and cold File state before the isolated call')
            gate = Barrier(8, timeout=12)
            def register(_):
                ctx = Context()
                gate.wait()
                native(ctx,None)
                check(word(c.addressof(ctx)) == 0 and word(c.addressof(ctx),12) == 0 and word(pool,8) == 2 and
                      pointer(pool,32) == field and pointer(pool,40), 'Concurrent framed initIDs did not publish both results')
                return get_native_id(),pointer(pool,32),pointer(pool,40)
            with ThreadPoolExecutor(8) as workers:
                observed = list(workers.map(register,range(8)))
            check(len({r[0] for r in observed}) == 8 and len({r[1:] for r in observed}) == 1 and word(file_class,8) == 2,
                  'Threads did not observe the same source registration')
            signature = c.WINFUNCTYPE(U,P,c.POINTER(c.c_wchar),U,U)
            registered = signature(pointer(pool,40))
            windows = c.WinDLL('kernel32',use_last_error=True)
            official = bind(windows,'GetFinalPathNameByHandleW',U,P,c.POINTER(c.c_wchar),U,U)
            sample = out/'文件路径 with spaces.txt'
            with sample.open('xb+') as stream:
                handle = msvcrt.get_osfhandle(stream.fileno())
                resolved = final_path(registered,handle)
                check(resolved == final_path(official,handle) and os.path.samefile(resolved,sample),
                      'Registered Windows function returned a different file or path')
            sample.unlink()
            # The incomplete, single-threaded setup can retain a monitor.
            # First prove that initIDs did not change any owner/acquisition,
            # then release precisely the setup thread's loans before heap close.
            check(host_held_monitors(heap) == setup_monitors, 'File registration changed monitor ownership')
            monitor_exit = bind(rt,'boom_monitor_exit',U,P,P,P)
            for obj,count in setup_monitors:
                for _ in range(count):
                    cleanup = Context()
                    check(monitor_exit(heap,obj,cleanup) == 0 and word(c.addressof(cleanup)) == 0,
                          'Could not release the preparation thread monitor')
            result = dict(parallel_OS_threads=len(observed),original_framed_method=member['method'],original_File_class=file['class_id'],
                          field_offset=word(field,8),field_width=word(field,20),nonzero_field_id=bool(pointer(pool,32)),
                          Unicode_file_handle_resolved=True,source_properties_setup_kind=word(c.addressof(prep)),
                          source_properties_setup_method=word(c.addressof(prep),8),setup_monitor_acquisitions_released=sum(n for _,n in setup_monitors),
                          registration_changed_monitor_ownership=False,provider_object_sha256=provider['object']['digest']['sha256'],
                          diagnostic_image_sha256=sha(image_path),source_proof_sha256=sha(selection/'selection-verification.json'))
        check(bind(image,'boom_release_trace_pool',U)() == 0, 'Java native frames remained active')
    finally:
        check(bind(rt,'boom_heap_destroy',U,P)(heap) == 1, 'Isolated heap did not close')
    return result


def verify_process_observation(selection, result):
    image = Path((selection/'native-execution-directory.txt').read_text(encoding='utf-8-sig').strip())
    manifest, proof, executed = (read(image/n) for n in ('vm-entry.json','verification.json','execution.json'))
    raw = (image/'vm-entry-status.bin').read_bytes()
    check(proof['verified'] and proof['source_manifest_sha256'] == sha(image/'vm-entry.json') and
          proof['executable_sha256'] == sha(image/'boom-vm-entry.exe') and
          Path(manifest['baseline_directory']).resolve() == selection and
          executed['source_verification_sha256'] == sha(image/'verification.json') and
          result['source_proof_sha256'] == manifest['accepted_source_verification_sha256'] and
          executed['native_report_sha256'] == hashlib.sha256(raw).hexdigest() and executed == read(selection/'execution.json'),
          'Native process receipt or source selection differs')
    check(len(raw) == 400 and struct.unpack_from('<II',raw) == (0x52454d56,10) and
          struct.unpack_from('<4I',raw,384) == (2,1,1,result['original_File_class']),
          'Native VM process did not publish the verified Windows filesystem registration')
    return dict(execution=str(image/'execution.json'),report_sha256=executed['native_report_sha256'],
                main_System_phases=executed['main_System_phases'],filesystem=executed['windows_filesystem'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--cold-worker',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    runtime, selection = args.runtime.resolve(), args.selection.resolve()
    if args.cold_worker:
        print(json.dumps(probe(runtime,selection,None,True)))
    else:
        out = ROOT/'.boom/winnt-file-id-tests'/uuid4().hex
        out.mkdir(parents=True)
        child = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--runtime',str(runtime),
                                '--selection',str(selection),'--cold-worker'],capture_output=True,text=True,timeout=30,check=True)
        result = probe(runtime,selection,out,False)
        result.update(passed=True,failed_initializer=json.loads(child.stdout),scope='original_framed_initIDs_in_isolated_FFI_host',
                      native_process_observation=verify_process_observation(selection,result),runtime_sha256=sha(runtime/'boom-runtime.dll'),
                      test_source_sha256=sha(__file__),game_started=False,world_created=False)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        (ROOT/'.boom/latest-winnt-file-id-test.txt').write_text(str(out),encoding='utf-8')
        print(out/'result.json')
