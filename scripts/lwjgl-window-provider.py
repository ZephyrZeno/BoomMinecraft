"""Generate the narrow Win64 GLFW window-call provider from the locked client.

LWJGL 3.3.3 generated C, org_lwjgl_system_JNI.c, Java_org_lwjgl_system_JNI_
invokePPPP__IIJJJJ: the last Java long selects the native function. Its five
arguments are two jint and three uintptr_t values. It returns uintptr_t.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
import zipfile


def script(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = script("runtime-provider-source")
Frames = script("verify-batch-frames")
IR = script("verify-translation-ir")
check = S.check
JNI = ("org/lwjgl/system/JNI", "invokePPPP", "(IIJJJJ)J")
GLFW = ("org/lwjgl/glfw/GLFW", "nglfwCreateWindow", "(IIJJJ)J")
EXPORT = "glfwCreateWindow"
KERNEL = S.ROOT / "native/providers/lwjgl_window_call.asm.inc"
METADATA_SHA1 = "9aa86ea608c3ec777dcdc09e6c5a06c85b53599e"
UPSTREAM = "https://github.com/LWJGL/lwjgl3/blob/3.3.3/modules/lwjgl/core/src/generated/c/org_lwjgl_system_JNI.c#L887-L890"


def sha(bytes_, algorithm="sha256"):
    return hashlib.new(algorithm, bytes_).hexdigest()


def binding_spec(data, export):
    """Accept exactly one named AMD64 DLL export backed by executable file bytes."""
    def unpack(fmt, offset):
        size = struct.calcsize("<" + fmt)
        check(0 <= offset <= len(data) - size, "PE field outside file")
        return struct.unpack_from("<" + fmt, data, offset)

    check(data[:2] == b"MZ" and 0 < len(data) < 2**32, "Not a supported PE file")
    pe, = unpack("I", 60)
    check(data[pe:pe + 4] == b"PE\0\0", "Invalid PE signature")
    machine, count = unpack("HH", pe + 4)
    optional_size, flags = unpack("HH", pe + 20)
    opt = pe + 24
    check(machine == 0x8664 and 0 < count <= 96 and flags & 0x2000 and
          optional_size >= 120 and unpack("H", opt)[0] == 0x20B and
          unpack("I", opt + 108)[0] >= 1, "Expected an AMD64 PE32+ DLL")
    sections = []
    for i in range(count):
        off = opt + optional_size + i * 40
        va, raw_size, raw_off = unpack("III", off + 12)
        attrs, = unpack("I", off + 36)
        check(raw_off + raw_size <= len(data), "Invalid section backing")
        sections.append((va, raw_size, raw_off, attrs))

    def locate(rva, size):
        matches = [(raw + rva - va, attrs) for va, length, raw, attrs in sections
                   if size > 0 and va <= rva and rva + size <= va + length]
        check(len(matches) == 1, "Unmapped or overlapping PE export")
        return matches[0]

    directory, size = unpack("II", opt + 112)
    check(directory and size >= 40, "DLL has no export directory")
    off, _ = locate(directory, size)
    funcs, names, addresses, strings, ordinals = unpack("IIIII", off + 20)
    check(0 < names <= funcs <= len(data) // 4, "Invalid export dimensions")
    functions = locate(addresses, funcs * 4)[0]
    pointers = locate(strings, names * 4)[0]
    ords = locate(ordinals, names * 2)[0]
    wanted = export.encode("ascii") + b"\0"
    candidates = []
    for n in range(names):
        ptr, = unpack("I", pointers + n * 4)
        pos, _ = locate(ptr, 1)
        if data[pos:pos + len(wanted)] != wanted:
            continue
        locate(ptr, len(wanted))
        ordinal, = unpack("H", ords + n * 2)
        check(ordinal < funcs, "Export ordinal outside function table")
        rva, = unpack("I", functions + ordinal * 4)
        check(rva and not directory <= rva < directory + size, "Forwarded or empty export")
        check(locate(rva, 1)[1] & 0x20000000, "Export is not executable")
        candidates.append(rva)
    check(len(candidates) == 1, "Expected one executable named export: " + export)
    return dict(size=len(data), sha256=sha(data), export=export, rva=candidates[0])


def source(plan, batch):
    lock = S.read(S.ART / "locks/client.json")
    check((lock["game_version"], lock["side"], lock["target"]["os"], lock["target"]["arch"]) ==
          ("1.21.1", "client", "windows", "x86_64"), "Expected locked 1.21.1 Win64 client")
    files = {item["id"]: item for item in lock["files"]}

    def locked(name):
        rec = files[name]
        path = S.checked(rec)
        data = path.read_bytes()
        check(sha(data, "sha1") == rec["digest"]["sha1"], "Lock SHA-1 mismatch: " + name)
        return data

    metadata = locked("version-metadata")
    check(sha(metadata, "sha1") == METADATA_SHA1, "Unexpected official 1.21.1 metadata digest")
    libraries = {lib["name"]: lib["downloads"]["artifact"] for lib in json.loads(metadata)["libraries"]}

    def jar(coordinate):
        rec = libraries[coordinate]
        key = "libraries/" + rec["path"]
        data = locked(key)
        check((len(data), sha(data, "sha1")) == (rec["size"], rec["sha1"]),
              "Library differs from official metadata: " + coordinate)
        return key, data

    plan = Path(plan).resolve()
    batch = Path(batch).resolve()
    check(plan.is_relative_to(S.ART) and batch.is_relative_to(S.ART), "Invalid batch/plan location")
    p = S.read(plan / "summary.json")
    b = S.read(batch / "summary.json")
    verified = S.read(batch / "verification.json")
    check(b["schema"] == 23 and b["frames"]["abi"] == 3 and verified["verified"] and
          verified["frames"]["verified"] and
          lock["fingerprint"] == p["input_fingerprint"] == b["input_fingerprint"],
          "Require the matching verified frame ABI3 client batch")
    # Stream the original plan once. The full digest, including ignored records,
    # anchors both matching Java method IDs before generating their symbols.
    keys = {JNI: None, GLFW: None}
    methods = p["artifacts"]["methods"]
    path = Path(methods["path"]).resolve()
    check(path == plan / "methods.jsonl", "Unexpected source method path")
    h = hashlib.sha256()
    hints = [f'"name":"{name}"'.encode() for _, name, _ in keys]
    with path.open("rb") as stream:
        for line in stream:
            h.update(line)
            if not any(marker in line for marker in hints):
                continue
            method = json.loads(line)
            symbol = method["symbol"]
            key = (symbol["owner"], symbol["name"], symbol["descriptor"])
            if key in keys:
                check(keys[key] is None and symbol["loader"] == "vanilla-application",
                      "Duplicate or mismatched source method")
                keys[key] = method
    check(h.hexdigest() == methods["digest"]["sha256"] and path.stat().st_size == methods["digest"]["size"]
          and all(keys.values()), "Source method inventory changed")
    classes = {}
    functions = []
    wanted_ids = {item["class_id"] for item in keys.values()}
    with S.checked(p["artifacts"]["classes"]).open(encoding="utf-8") as stream:
        for line in stream:
            cl = json.loads(line)
            if cl["id"] in wanted_ids:
                classes[cl["id"]] = cl
            if cl["name"] == GLFW[0] + "$Functions" and cl["origin"]["loader"] == "vanilla-application":
                functions.append(cl)
    check(len(functions) == 1, "Missing GLFW function table source")
    table = functions[0]
    evidence = []
    for key, coordinate in [(JNI, "org.lwjgl:lwjgl:3.3.3"), (GLFW, "org.lwjgl:lwjgl-glfw:3.3.3")]:
        item = keys[key]
        cls = classes[item["class_id"]]
        library_id, library = jar(coordinate)
        owner, name, desc = key
        with zipfile.ZipFile(io.BytesIO(library)) as archive:
            raw = archive.read(owner + ".class")
            if key == GLFW:
                table_raw = archive.read(table["name"] + ".class")
        check(sha(raw) == cls["origin"]["sha256"] == item["class_sha256"] and
              cls["origin"]["source_id"] == library_id and cls["name"] == owner,
              "Plan identity differs from locked class")
        original, members = Frames.original_methods(raw)
        matching = [m for m in members if (m["name"], m["descriptor"]) == (name, desc)]
        check(original == owner and len(matching) == 1, "Original method missing")
        method = matching[0]
        check(method["access"] == item["access"], "Method access differs")
        if key == JNI:
            check(method["access"] & 0x109 == 0x109 and method["code"] is None and item["code_sha256"] is None,
                  "JNI method is not a public static native declaration")
        else:
            code = method["code"][0]
            parsed = IR.Source(raw)
            check(sha(code) == item["code_sha256"] and code[0] == 0xB2 and code[14] == 0xB8,
                  "Unexpected nglfwCreateWindow bytecode")
            for pc, expected in [(0, (GLFW[0] + "$Functions", "CreateWindow", "J")), (14, JNI)]:
                member = parsed.member(int.from_bytes(code[pc + 1:pc + 3], "big"))
                check(tuple(member[k] for k in ("owner", "name", "descriptor")) == expected,
                      "Unexpected GLFW function/call target")
            check(table["origin"]["source_id"] == library_id and table["origin"]["sha256"] == sha(table_raw),
                  "GLFW function table differs from locked class")
            parsed_table = IR.Source(table_raw)
            clinit = next(m for m in parsed_table.methods if (m["name"], m["descriptor"]) == ("<clinit>", "()V"))
            init = parsed_table.code(clinit)["bytes"]
            # invokestatic GLFW.access$000; ldc "glfwCreateWindow"; invokestatic
            # APIUtil.apiGetFunctionAddress; putstatic GLFW$Functions.CreateWindow.
            check([init[i] for i in (308, 311, 313, 316)] == [0xB8, 0x12, 0xB8, 0xB3] and
                  parsed_table.symbol(init[312]) == {"StringUtf16": list(EXPORT.encode("ascii"))},
                  "Original window export string binding differs")
            for pc, expected in [(308, (GLFW[0], "access$000", "()Lorg/lwjgl/system/SharedLibrary;")),
                                 (313, ("org/lwjgl/system/APIUtil", "apiGetFunctionAddress",
                                        "(Lorg/lwjgl/system/FunctionProvider;Ljava/lang/String;)J")),
                                 (316, (table["name"], "CreateWindow", "J"))]:
                member = parsed_table.member(int.from_bytes(init[pc + 1:pc + 3], "big"))
                check(tuple(member[k] for k in ("owner", "name", "descriptor")) == expected,
                      "Original GLFW export resolution differs")
            ordinals = [n for n, field in enumerate(parsed_table.fields) if
                        (field["name"], field["descriptor"], field["access"]) == ("CreateWindow", "J", 25)]
            check(len(ordinals) == 1, "Missing original public static final window function")
            table_proof = dict(cls=table["id"], field=ordinals[0], class_sha256=sha(table_raw),
                               clinit_sha256=sha(init), resolution_pc=313, publication_pc=316)
        # Java batch schema 23 groups classes by class ID in numbered zip shards.
        shard = b["shards"][item["class_id"] // 256]
        with zipfile.ZipFile(S.checked(shard["zip"])) as archive:
            record = json.loads(archive.read(f'classes/{item["class_id"]:06d}.json'))
        entries = [m for m in record["methods"] if m["id"] == item["id"]]
        check(record["class_id"] == item["class_id"] and record["source_sha256"] == sha(raw) and
              len(entries) == 1 and (entries[0]["name"], entries[0]["descriptor"],
                                     entries[0]["code_sha256"]) == (name, desc, item["code_sha256"]) and
              entries[0]["assembly_emitted"] == (key == GLFW), "Client batch method mismatch")
        evidence.append(dict(owner=owner, name=name, descriptor=desc, method=item["id"], cls=item["class_id"],
                             class_sha256=sha(raw), code_sha256=item["code_sha256"], stage=entries[0]["stage"]))
        if key == GLFW:
            unit = shard["units"][entries[0]["assembly_unit"]]["assembly"]
            S.checked(unit)
            evidence[-1]["assembly_unit"] = unit
    _, native_archive = jar("org.lwjgl:lwjgl-glfw:3.3.3:natives-windows")
    with zipfile.ZipFile(io.BytesIO(native_archive)) as archive:
        image = archive.read("windows/x64/org/lwjgl/glfw/glfw.dll")
    check(image == locked("native/glfw.dll"), "Native DLL differs from official Windows archive")
    return dict(metadata_sha1=METADATA_SHA1, fingerprint=lock["fingerprint"], methods=evidence, function_table=table_proof,
                upstream_native_signature=UPSTREAM, module=binding_spec(image, EXPORT))


def caller_assembly(proof):
    """Extract the two original emitted procedures, byte for byte after newline normalization."""
    native, caller = proof["methods"]
    table = proof["function_table"]
    text = S.checked(caller["assembly_unit"]).read_text(encoding="utf-8")
    name = f'boom_m{caller["method"]}'
    chunks = []
    for proc in (name, name + "_body"):
        matches = re.findall(r"^" + proc + r" PROC FRAME\n.*?^" + proc + r" ENDP$", text, re.M | re.S)
        check(len(matches) == 1, "Original emitted GLFW procedure missing")
        chunks.extend(matches)
    bodies = "\n".join(chunks)
    field = f'boom_s{table["cls"]}_{table["field"]}'
    target = f'boom_m{native["method"]}'
    check(f'mov rax, QWORD PTR [{field}]' in bodies and f'call {target}\n' in bodies,
          "Emitted GLFW caller/export field differs")
    return f"""option casemap:none
EXTERN boom_class{caller['cls']}:BYTE, boom_class{table['cls']}:BYTE
EXTERN boom_trace_pool:BYTE, boom_trace_method{caller['method']}:BYTE, {field}:QWORD
EXTERN boom_class_ensure32:PROC, boom_trace_enter:PROC, boom_trace_leave:PROC
EXTERN boom_exception_materialize:PROC, {target}:PROC
PUBLIC {name}
.code
{bodies}
END
"""


def assembly(method, spec):
    """The normal build supplies only source()'s spec. Fixtures use a separate image."""
    mid = method["method"]
    cid = method["cls"]
    digest_bytes = ",".join(str(b) for b in bytes.fromhex(spec["sha256"]))
    check(spec["export"] == EXPORT, "Unexpected typed window export")
    return f"""option casemap:none
EXTERN boom_class_ensure32:PROC
EXTERN boom_trace_enter:PROC
EXTERN boom_trace_leave:PROC
EXTERN boom_trace_pool:BYTE
EXTERN boom_trace_method{mid}:BYTE
EXTERN boom_class{cid}:BYTE
PUBLIC boom_m{mid}
PUBLIC boom_lwjgl_window_pool
.const
lwjgl_window_digest BYTE {digest_bytes}
lwjgl_window_name BYTE "{EXPORT}",0
ALIGN 8
lwjgl_window_spec DWORD {spec['size']}, {spec['rva']}
    QWORD OFFSET lwjgl_window_digest, OFFSET lwjgl_window_name
.data
ALIGN 8
boom_lwjgl_window_pool DWORD 314A574Ch,1
    QWORD 0, OFFSET lwjgl_window_spec, 0, 0, 0
{KERNEL.read_text(encoding="utf-8")}
{Frames.native_adapter(mid, cid, "boom_lwjgl_window_pool", "boom_provider_lwjgl_window_call", 0)}
END
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    proof = source(args.plan, args.batch)
    out = args.out.resolve()
    check(out.is_relative_to(S.ART), "Build output belongs in project .boom")
    out.mkdir(parents=True, exist_ok=False)
    (out / "lwjgl-window-provider.asm").write_text(assembly(proof["methods"][0], proof["module"]), encoding="utf-8")
    S.write(out / "source.json", proof)
    print(out)


if __name__ == "__main__":
    main()
