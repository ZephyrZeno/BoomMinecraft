"""Verify a locked production COFF and exercise the same assembly with an inert DLL.

Run on Win64 with --plan, --batch, --assembler ml64.exe, --linker link.exe and
--sdk-lib pointing to the Windows SDK um/x64 directory.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import importlib.util
from pathlib import Path
import struct
import subprocess
import threading
import uuid


def load():
    path = Path(__file__).with_name("lwjgl-window-provider.py")
    spec = importlib.util.spec_from_file_location("lwjgl_window_provider", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load()
check = P.check
Q = C.c_uint64
D = C.c_uint32
V = C.c_void_p
MASK = 2**64 - 1
FIXTURE = Path(__file__).with_name("tests") / "lwjgl-window-fixture.asm"
IMPORTS = {
    "GetModuleHandleExW", "GetModuleFileNameW", "FreeLibrary", "GetProcAddress",
    "AcquireSRWLockExclusive", "ReleaseSRWLockExclusive", "VirtualAlloc", "VirtualFree",
    "CreateFileW", "GetFileSizeEx", "CreateFileMappingW", "MapViewOfFile", "UnmapViewOfFile",
    "CloseHandle", "BCryptHash",
}


class Binding(C.Structure):
    _fields_ = [("magic", D), ("abi", D), ("reserved", Q), ("spec", V),
                ("approved", V), ("module", V), ("lock", V)]


class Spec(C.Structure):
    _fields_ = [("size", D), ("rva", D), ("digest", V), ("name", V)]


class Context(C.Structure):
    _fields_ = [("kind", D), ("pc", D), ("method", D), ("depth", D),
                ("throwable", Q), ("plan", Q)]


def typed(lib, name, args, result):
    fn = getattr(lib, name)
    fn.argtypes, fn.restype = args, result
    return fn


def fixture_frames(proof):
    """Check the generated native frame's calling contract, using isolated trace/class stand-ins."""
    method, caller = proof["methods"]
    table = proof["function_table"]
    cid, mid = method["cls"], method["method"]
    caller_mid = caller["method"]
    field = f'boom_s{table["cls"]}_{table["field"]}'
    return f"""option casemap:none
.data
PUBLIC boom_class{cid}, boom_trace_pool, boom_trace_method{mid}
PUBLIC boom_class{caller["cls"]}, boom_class{table["cls"]}, boom_trace_method{caller_mid}
PUBLIC entered, left, callerEntered, materialized, {field}
boom_class{cid} BYTE 0
boom_class{caller["cls"]} BYTE 0
boom_class{table["cls"]} BYTE 0
boom_trace_pool BYTE 0
boom_trace_method{mid} BYTE 0
boom_trace_method{caller_mid} BYTE 0
ALIGN 8
entered QWORD 0
left QWORD 0
callerEntered QWORD 0
materialized QWORD 0
{field} QWORD 0
.code
PUBLIC boom_class_ensure32, boom_trace_enter, boom_trace_leave, boom_exception_materialize
boom_class_ensure32 PROC
    lea rax,boom_class{cid}
    cmp rcx,rax
    je known_class
    lea rax,boom_class{caller["cls"]}
    cmp rcx,rax
    je known_class
    lea rax,boom_class{table["cls"]}
    cmp rcx,rax
    jne bad_class
known_class:
    xor eax,eax
    ret
bad_class:
    mov DWORD PTR [rdx],7
    mov eax,7
    ret
boom_class_ensure32 ENDP
boom_trace_enter PROC
    lea rax,boom_trace_pool
    cmp rcx,rax
    jne bad_enter
    lea rax,boom_trace_method{mid}
    cmp r8,rax
    je known_frame
    lea rax,boom_trace_method{caller_mid}
    cmp r8,rax
    jne bad_enter
    lock inc QWORD PTR callerEntered
known_frame:
    cmp QWORD PTR [rdx],0
    jne bad_enter
    cmp DWORD PTR [r9+12],0
    je bad_enter
    mov QWORD PTR [rdx],6127
    lock inc QWORD PTR entered
    xor eax,eax
    ret
bad_enter:
    mov DWORD PTR [r9],7
    mov eax,7
    ret
boom_trace_enter ENDP
boom_trace_leave PROC
    lea rax,boom_trace_pool
    cmp rcx,rax
    jne bad_leave
    cmp QWORD PTR [rdx],6127
    jne bad_leave
    cmp DWORD PTR [r8+12],0
    je bad_leave
    lock inc QWORD PTR left
    ret
bad_leave:
    mov DWORD PTR [r8],7
    ret
boom_trace_leave ENDP
boom_exception_materialize PROC
    lock inc QWORD PTR materialized
    xor eax,eax
    ret
boom_exception_materialize ENDP
END
"""


def rol(x, n):
    return ((x << n) | (x >> (64 - n))) & MASK


def expected(a, b, c, d, e):
    return rol(rol(rol(rol(a & 0xFFFFFFFF, 11) ^ (b & 0xFFFFFFFF), 57) ^ c, 17) ^ d, 23) ^ e


def execute(out, proof, probe_spec):
    method, caller = proof["methods"]
    table = proof["function_table"]
    check(C.sizeof(V) == 8 and C.sizeof(Binding) == 48 and C.sizeof(Spec) == 24 and
          C.sizeof(Context) == 32, "Expected Windows x64 provider layout")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    load_lib = typed(kernel, "LoadLibraryW", [C.c_wchar_p], V)
    free = typed(kernel, "FreeLibrary", [V], D)
    addr = typed(kernel, "GetProcAddress", [V, C.c_char_p], V)
    # Only load the two local test DLLs. The production GLFW image is read as bytes.
    module = load_lib(str(out / "probe.dll"))
    check(module, "Fixture DLL failed to load")
    runtime = C.WinDLL(str(out / "fixture-adapter.dll"))
    bind = typed(runtime, "boom_provider_lwjgl_window_bind", [V, V], D)
    service = typed(runtime, "boom_provider_lwjgl_window_call", [V, V, V, D], Q)
    wrapper = typed(runtime, f'boom_m{method["method"]}', [V, V], Q)
    glfw_call = typed(runtime, f'boom_m{caller["method"]}', [V, V], Q)
    field = Q.in_dll(runtime, f'boom_s{table["cls"]}_{table["field"]}')
    pool = Binding.in_dll(runtime, "boom_lwjgl_window_pool")
    poolptr = C.addressof(pool)
    target = addr(module, P.EXPORT.encode("ascii"))
    other = addr(module, b"differentFunction")
    calls = Q.from_address(addr(module, b"observedCalls"))
    alignment = Q.from_address(addr(module, b"alignmentFailures"))
    unexpected = Q.from_address(addr(module, b"unexpectedCalls"))
    entered = Q.in_dll(runtime, "entered")
    left = Q.in_dll(runtime, "left")
    caller_frames = Q.in_dll(runtime, "callerEntered")
    materialized = Q.in_dll(runtime, "materialized")
    check(target == module + probe_spec["rva"] and other and other != target, "Invalid fixture PE target")
    kernel_addr = addr(kernel._handle, b"GetLastError")

    def context(kind=0, depth=0):
        return Context(kind, 0x12345678, method["method"], depth, 0, 0x771126)

    def invoke(values, fn=target, kind=0, depth=0):
        ctx = context(kind, depth)
        args = (Q * 6)(*values, fn)
        res = wrapper(C.byref(ctx), args)
        check((ctx.pc, ctx.method, ctx.depth, ctx.throwable, ctx.plan) ==
              (0x12345678, method["method"], depth, 0, 0x771126),
              "Generated frame damaged managed context")
        return res, ctx.kind

    def through_java(values):
        ctx = context()
        result = glfw_call(C.byref(ctx), (Q * 5)(*values))
        check((ctx.pc, ctx.method, ctx.depth, ctx.throwable, ctx.plan) ==
              (0x12345678, method["method"], 0, 0, 0x771126), "Original GLFW caller damaged context")
        return result, ctx.kind

    def rejected_spec(metadata, name=P.EXPORT):
        digest = C.create_string_buffer(bytes.fromhex(metadata["sha256"]))
        export_name = C.create_string_buffer(name.encode("ascii"))
        spec = Spec(metadata["size"], metadata["rva"], C.addressof(digest), C.addressof(export_name))
        binding = Binding(pool.magic, pool.abi, 0, C.addressof(spec), None, None, None)
        result = bind(C.byref(binding), module)
        check(result and binding.approved is None and binding.module is None,
              "An unverified fixture export was published")
        return result

    zero = [0] * 5
    check(invoke(zero) == (0, 20) and not calls.value, "Unbound target executed")
    check(bind(None, module) == 87 and bind(poolptr, None) == 87, "Invalid binder input")
    check(bind(poolptr, module + 1) == 13, "Interior address accepted as module handle")
    check(bind(poolptr, kernel._handle) == 13, "Module of a different identity bound")
    check(rejected_spec(proof["module"]) == 13, "A fixture DLL matched the official game policy")
    check(rejected_spec(dict(probe_spec, rva=probe_spec["rva"] + 1)) == 13, "Incorrect RVA accepted")
    check(rejected_spec(dict(probe_spec, size=probe_spec["size"] + 1)) == 13, "Incorrect size accepted")
    bad_sha = (int(probe_spec["sha256"][-2:], 16) ^ 1).to_bytes(1, "big").hex()
    check(rejected_spec(dict(probe_spec, sha256=probe_spec["sha256"][:-2] + bad_sha)) == 13,
          "Incorrect final digest byte accepted")
    check(rejected_spec(probe_spec, "missingWindowFunction") == 127, "Absent export accepted")
    check(rejected_spec(probe_spec, "differentFunction") == 13, "Different same-module export accepted")
    check(not pool.approved and not pool.module, "Failed binding left a published address")
    workers = 8
    barrier = threading.Barrier(workers)

    def register(_):
        barrier.wait(timeout=15)
        return bind(poolptr, module)

    with ThreadPoolExecutor(workers) as executor:
        check(list(executor.map(register, range(workers))) == [0] * workers, "Concurrent registration failure")
    check(pool.approved == target and pool.module == module and bind(poolptr, module) == 0 and
          bind(poolptr, kernel._handle) == 170, "Lost or replaced published target")
    check(free(module), "Unable to drop the test owner's loader reference")
    for fn in (0, other, kernel_addr, target + 1):
        check(invoke(zero, fn) == (0, 20), "Non-registered code pointer accepted")
    check(invoke(zero, kind=11) == (0, 11) and invoke(zero, depth=128) == (0, 10),
          "Generated frame mishandled pending exception or stack limit")
    invalid = Binding(0, 1, 0, None, None, None, None)
    valid_args = (Q * 6)(*zero, target)
    for argv, pool_arg, op in [(None, poolptr, 0), (valid_args, None, 0),
                               (valid_args, C.byref(invalid), 0), (valid_args, poolptr, 1)]:
        ctx = context()
        check(service(C.byref(ctx), argv, pool_arg, op) == 0 and ctx.kind == 7,
              "Invalid service arguments accepted")
    check(service(None, None, None, 1) == 0 and not calls.value, "Invalid call reached fixture")
    field.value = other
    check(through_java(zero) == (0, 20) and materialized.value == 1 and not calls.value,
          "An unregistered address in GLFW$Functions.CreateWindow reached native code")
    field.value = target
    samples = [zero, [0, 0, 0, 0, MASK], [0xFEDCBA98FFFFFFFF, 0xACED008080000020,
               0xFEDCBA9876543210, 0x8877665544332211, 0x8192837465ABCDEF]]
    for args in samples:
        result = expected(*args), 0
        check(invoke(args) == result and through_java(args) == result,
              "Java operand marshalling, native registers, stack or return value differed")

    def repeat(n):
        for i in range(128):
            k = n * 128 + i
            args = [0xFFFF123400000000 + k, MASK - k, rol(k + 91, 43), rol(2 * k + 3, 39), rol(k + 15, 59)]
            check(through_java(args) == (expected(*args), 0), "Concurrent Java/native argument corruption")

    with ThreadPoolExecutor(workers) as executor:
        list(executor.map(repeat, range(workers)))
    java_success = len(samples) + workers * 128
    check(calls.value == len(samples) + java_success and not alignment.value and not unexpected.value and
          caller_frames.value == java_success + 1 and materialized.value == 1 and
          entered.value == left.value == len(samples) + 5 + 2 * caller_frames.value,
          "Unexpected calls, stack alignment or unbalanced generated frames")
    return dict(successful_target_calls=calls.value, registration_threads=workers,
                calls_via_original_glfw_assembly=java_success, concurrent_calls=workers * 128,
                generated_java_and_native_frames_entered=entered.value,
                generated_java_and_native_frames_left=left.value, alignment_failures=alignment.value,
                rejected_targets_executed=unexpected.value, after_owner_release=True,
                zero_and_full_width_return=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "batch", "assembler", "linker", "sdk-lib"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    proof = P.source(args.plan, args.batch)
    method = proof["methods"][0]
    out = P.S.ART / "lwjgl-window-call-tests" / uuid.uuid4().hex
    out.mkdir(parents=True)
    print(out, flush=True)

    def run(command):
        result = subprocess.run(list(map(str, command)), cwd=out, timeout=50,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(result.stdout.decode("mbcs", errors="replace"))

    def assemble(name, text):
        asm = out / (name + ".asm")
        asm.write_text(text, encoding="utf-8")
        obj = out / (name + ".obj")
        run([args.assembler, "/nologo", "/c", "/Fo" + str(obj), asm])
        return obj

    def link(name, objs, exports, libs=()):
        dll = out / (name + ".dll")
        run([args.linker, "/nologo", "/dll", "/noentry", "/machine:x64", "/nodefaultlib",
             "/incremental:no", "/out:" + str(dll), *objs, *["/export:" + s for s in exports], *libs])
        return dll

    prod = assemble("production", P.assembly(method, proof["module"]))
    defined, undefined = P.script("verify-batch-assembly").coff_symbols(prod, IMPORTS)
    entry = f'boom_m{method["method"]}'
    expected_defs = {entry, "boom_lwjgl_window_pool", "boom_provider_lwjgl_window_bind",
                     "boom_provider_lwjgl_window_call"}
    expected_deps = {f'boom_class{method["cls"]}', f'boom_trace_method{method["method"]}',
                     "boom_class_ensure32", "boom_trace_pool", "boom_trace_enter", "boom_trace_leave"}
    check(defined >= expected_defs and undefined == IMPORTS | expected_deps, "Unexpected production COFF ABI")
    probe_obj = assemble("probe", FIXTURE.read_text(encoding="utf-8"))
    _, probe_imports = P.script("verify-batch-assembly").coff_symbols(probe_obj)
    check(not probe_imports, "The test target must not depend on a graphics/display library")
    probe_dll = link("probe", [probe_obj], [P.EXPORT, "differentFunction", "observedCalls,DATA",
                     "alignmentFailures,DATA", "unexpectedCalls,DATA", "forwarded=KERNEL32.Sleep"],
                     [args.sdk_lib / "kernel32.lib"])
    data = probe_dll.read_bytes()
    pe, = struct.unpack_from("<I", data, 0x3C)
    check(struct.unpack_from("<II", data, pe + 24 + 120) == (0, 0), "Test DLL acquired imports")
    probe = P.binding_spec(data, P.EXPORT)
    for bad_export in ("missingExport", "observedCalls", "forwarded"):
        try:
            P.binding_spec(data, bad_export)
        except ValueError:
            continue
        raise ValueError("Invalid executable PE export accepted: " + bad_export)
    fixture = assemble("fixture-adapter", P.assembly(method, probe))
    frames = assemble("fixture-class-and-trace", fixture_frames(proof))
    caller = assemble("original-glfw-caller", P.caller_assembly(proof))
    table = proof["function_table"]
    link("fixture-adapter", [fixture, frames, caller], [entry, "boom_lwjgl_window_pool,DATA", "entered,DATA",
         "left,DATA", "callerEntered,DATA", "materialized,DATA", f'boom_m{proof["methods"][1]["method"]}',
         f'boom_s{table["cls"]}_{table["field"]},DATA', "boom_provider_lwjgl_window_bind", "boom_provider_lwjgl_window_call"],
         [args.sdk_lib / "kernel32.lib", args.sdk_lib / "synchronization.lib", args.sdk_lib / "bcrypt.lib"])
    results = execute(out, proof, probe)
    proof.update(scope="locked_original_client_method_and_headless_Win64_native_adapter_fixture",
                 production_coff=P.S.artifact(prod), provider_kernel=P.S.artifact(P.KERNEL),
                 original_glfw_caller_coff=P.S.artifact(caller), test_target=probe, results=results,
                 frame_services="fixture class, static field, trace and exception materialization",
                 real_glfw_image_loaded=False, game_started=False, window_created=False)
    P.S.write(out / "verification.json", proof)
    print(results)


if __name__ == "__main__":
    main()
