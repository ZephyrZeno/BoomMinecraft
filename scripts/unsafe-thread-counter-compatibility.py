"""Prove the inherited Unsafe thread-counter dependency against a tested runtime."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

COUNTER = "boom_threads_id_memory"
REGISTRY = "native/runtime/thread_registry.asm"
FIELD = "native/runtime/java_unsafe_fields.asm"


def check(test, reason):
    if not test:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def procedures(text):
    result = {}
    for m in re.finditer(r"(?ms)^(\w+) PROC[^\n]*\n.*?^\1 ENDP[^\n]*", text):
        check(m[1] not in result, "Duplicate registry procedure")
        result[m[1]] = m[0]
    return result


def instructions(text):
    return [line.partition(";")[0].strip() for line in text.splitlines() if line.partition(";")[0].strip()]


def source_contract(old, new):
    before, after = procedures(old), procedures(new)
    priority = "boom_threads_set_priority"
    check(set(after) - set(before) == {priority} and all(after.get(n) == body for n, body in before.items()),
          "An inherited thread registry procedure changed")
    # Remove ONLY the accepted addition. All original instructions, declarations,
    # sections, globals, assembler options and any EQU/directive must still agree.
    clean = instructions(new.replace(after[priority], "", 1))
    for decl in ("EXTERN OpenThread:PROC", "EXTERN SetThreadPriority:PROC", "PUBLIC " + priority):
        check(clean.count(decl) == 1, "Unexpected priority import/export")
        clean.remove(decl)
    table = [".const", "ALIGN 4", "threads_java_priorities DWORD -2,-2,-1,-1,0,0,1,1,2,2", ".code"]
    i = clean.index(table[2]) - 2
    check(clean[i:i + 4] == table, "Unexpected registry priority data")
    del clean[i:i + 4]
    check(clean == instructions(old), "Old registry data, assembler options, definitions or code changed")
    body = before[COUNTER]
    calls = re.findall(r"(?m)^\s*call (\w+)\s*$", body)
    check(calls == ["AcquireSRWLockShared", "ReleaseSRWLockShared"] and
          all("EXTERN " + fn + ":PROC" in clean for fn in calls), "Counter call graph changed")
    globals_ = [line for line in clean if line in ("threads_lock QWORD 0", "threads_active QWORD 0")]
    check(globals_ == ["threads_lock QWORD 0", "threads_active QWORD 0"] and
          "cmp rdi,QWORD PTR [r10+8]" in body and "add r10,32" in body and
          "lock cmpxchg QWORD PTR [r10],rdx" in body, "Thread counter domain or storage changed")
    # The new priority path may compare to active. No update, exchange or
    # address-taking of either shared global is admitted by this proof.
    uses = [line for line in instructions(after[priority]) if re.search(r"\bthreads_(?:lock|active)\b", line)]
    check(uses and all(line in ("lea rcx,threads_lock", "cmp QWORD PTR threads_active,rbx") for line in uses),
          "Priority path may modify the Unsafe counter domain")
    return dict(entry=COUNTER, entry_source_sha256=sha(body.encode()), identical_original_procedures=len(before),
                new_procedures=[priority], globals=globals_, direct_system_calls=calls,
                registry_identity_offset=8, counter_offset=32,
                same_create_next_address_destroy=[n for n in ("boom_threads_create", "boom_threads_next_id",
                    "boom_threads_id_address", "boom_threads_destroy") if n in before])


def executable_slice(path):
    """Read the tested DLL's exported counter size from the x64 unwind directory."""
    data = path.read_bytes()
    def read(fmt, pos): return struct.unpack_from("<" + fmt, data, pos)
    pe, = read("I", 60)
    check(data[:2] == b"MZ" and data[pe:pe+4] == b"PE\0\0" and read("H", pe+4)[0] == 0x8664,
          "Invalid runtime PE machine")
    opt = pe + 24
    off = opt + read("H", pe + 20)[0]
    sections = [read("IIII", off + i*40 + 8) for i in range(read("H", pe + 6)[0])]
    def loc(rva, size):
        candidates = [raw + rva - va for _, va, length, raw in sections if va <= rva and rva + size <= va+length]
        check(len(candidates) == 1 and candidates[0] + size <= len(data), "Unmapped runtime image range")
        return candidates[0]
    exports, esize = read("II", opt + 112)
    funcs, names, addresses, pointers, ordinals = read("IIIII", loc(exports, esize) + 20)
    target = []
    for i in range(names):
        name, = read("I", loc(pointers + 4*i, 4))
        p = loc(name, 1)
        if data[p:data.index(b"\0", p)] != COUNTER.encode():
            continue
        ordinal, = read("H", loc(ordinals + 2*i, 2))
        check(ordinal < funcs, "Invalid counter export ordinal")
        target.append(read("I", loc(addresses + 4*ordinal, 4))[0])
    check(len(target) == 1 and not exports <= target[0] < exports + esize, "Missing direct counter export")
    unwind, size = read("II", opt + 112 + 3*8)
    check(size and size % 12 == 0, "Invalid x64 runtime unwind directory")
    start = loc(unwind, size)
    entries = [row for row in struct.iter_unpack("<III", data[start:start+size]) if row[0] == target[0]]
    check(len(entries) == 1, "Counter native extent not found")
    lo, hi, _ = entries[0]
    check(0 < hi-lo <= 4096, "Unexpected native counter extent")
    start = loc(lo, hi-lo)
    return lo, data[start:start + hi-lo]


def object_slice(path, size):
    data = path.read_bytes()
    machine, sections, _, table, count, opt, _ = struct.unpack_from("<HHIIIHH", data)
    check(machine == 0x8664 and opt == 0, "Expected AMD64 registry COFF")
    strings = table + 18*count
    names, selected = {}, []
    i = 0
    while i < count:
        at = table + i*18
        raw = data[at:at+8]
        if raw[:4] == bytes(4):
            j = strings + int.from_bytes(raw[4:], "little")
            raw = data[j:data.index(0, j)]
        name = raw.rstrip(b"\0").decode("ascii")
        names[i] = name
        value, section, _, storage, aux = struct.unpack_from("<IhHBB", data, at+8)
        if name == COUNTER and section > 0 and storage == 2:
            selected.append((section, value))
        i += 1+aux
    check(len(selected) == 1, "Missing unique native registry entry")
    section, start = selected[0]
    check(section <= sections, "Invalid counter section")
    h = 20 + (section-1)*40
    length, raw, rel = struct.unpack_from("<III", data, h+16)
    check(start+size <= length, "Counter escapes native section")
    relocs = []
    for i in range(struct.unpack_from("<H", data, h+32)[0]):
        off, symbol, kind = struct.unpack_from("<IIH", data, rel+10*i)
        if start <= off < start+size:
            check(kind == 4 and off+4 <= start+size and symbol in names, "Unexpected native counter relocation")
            relocs.append((off-start, names[symbol]))
    return data[raw+start:raw+start+size], relocs


def prove(root, art, old_path, runtime, assembler, base, artifact):
    check(old_path.is_relative_to(art) and runtime.is_relative_to(art), "Registry source/runtime must be project artifacts")
    old, current = old_path.read_bytes(), (root / REGISTRY).read_bytes()
    old_digest = base["unsafe_memory"]["kernel_sha256"][REGISTRY]
    check(sha(old) == old_digest and sha(current) != old_digest, "Old registry snapshot or new dependency differs")
    field_sources = [old_path.parent / "java_unsafe_fields.asm", root / FIELD]
    check(sha(field_sources[0].read_bytes()) == base["unsafe_fields"]["kernel_sha256"][FIELD],
          "Original Unsafe caller snapshot changed")
    for f in field_sources:
        text = f.read_text(encoding="utf-8-sig")
        check(re.findall(r"(?mi)^EXTERN (boom_threads_\w+):PROC\s*$", text) == [COUNTER] and
              re.findall(r"(?mi)^\s*call (boom_threads_\w+)\s*$", text) == [COUNTER],
              "Source Unsafe calls another registry procedure")
    proof = source_contract(old_path.read_text(encoding="utf-8-sig"), (root / REGISTRY).read_text(encoding="utf-8-sig"))
    manifest = json.loads((runtime / "runtime.json").read_text(encoding="utf-8-sig"))
    dll = (runtime / "boom-runtime.dll").resolve()
    check(Path(manifest["dll"]).resolve() == dll and manifest["implementation_language"] == "x86-64 MASM assembly"
          and not any(manifest[k] for k in ("java_runtime","rust_runtime","c_runtime")) and
          manifest["sources"][REGISTRY] == sha(current) and manifest["sources"][FIELD] == sha(field_sources[1].read_bytes()) and
          artifact(dll)["digest"]["sha256"] == manifest["sha256"], "Tested runtime differs from current assembly sources")
    rva, linked_code = executable_slice(dll)
    with tempfile.TemporaryDirectory(prefix="counter-proof-", dir=art) as tmp:
        # Reassemble the hash-checked old source independently. Neither image is loaded.
        obj = Path(tmp)/"thread_registry.obj"
        subprocess.run([str(assembler), "/nologo", "/c", "/Fo"+str(obj), str(old_path)],
                       cwd=tmp, check=True, stdout=subprocess.PIPE, timeout=90)
        original_code, original_refs = object_slice(obj, len(linked_code))
    current_code, current_refs = object_slice(runtime / "thread_registry.obj", len(linked_code))
    check((original_code, original_refs) == (current_code, current_refs), "Old and current counter code/relocations differ")
    actual, expected = bytearray(linked_code), bytearray(current_code)
    for offset, _ in current_refs:
        actual[offset:offset+4] = bytes(4)
        expected[offset:offset+4] = bytes(4)
    check(actual == expected and {name for _,name in current_refs} ==
          {"threads_lock","threads_active","AcquireSRWLockShared","ReleaseSRWLockShared"},
          "Tested DLL counter machine code or dependency set differs")
    return dict(previous=artifact(old_path), current=artifact(root / REGISTRY), previous_unsafe_caller=artifact(field_sources[0]),
                runtime_manifest=artifact(runtime/"runtime.json"), runtime_dll=artifact(dll),
                runtime_registry_object=artifact(runtime/"thread_registry.obj"), contract=proof, rva=rva,
                code_bytes=len(linked_code), coff_code_sha256=sha(current_code), dll_code_sha256=sha(linked_code),
                relocations=[dict(offset=at, target=target) for at, target in current_refs])
