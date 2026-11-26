"""Derive and verify a sparse UFMP ABI2 batch from an accepted ABI1 batch.

The derived summary keeps the original paths of all unchanged artifacts. Only
the unit containing UFMP128 is assembled. The derivation is not a full-batch
verification receipt, source profile rebind or runtime execution.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile


def script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


U = script("verify-batch-unsafe-fields")
A = script("verify-batch-assembly")
ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / ".boom"
KERNEL = "native/runtime/java_unsafe_fields.asm"
CHECK = A.check


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def artifact(path):
    return dict(path=str(path.resolve()), digest=A.file_digest(path))


def checked(record, directory):
    path = Path(record["path"]).resolve()
    CHECK(path.is_relative_to(directory.resolve()), "Source artifact escapes " + str(directory))
    CHECK(A.file_digest(path) == record["digest"], "Source artifact changed: " + str(path))
    return path


def sparse_artifacts(base, derived_batch):
    """Same verified-assembly callback contract, using only the two proven roots."""
    def resolve(root, record, subdirectory=""):
        CHECK(Path(root).resolve() == derived_batch, "Unexpected sparse verification root")
        path = Path(record["path"]).resolve()
        candidates = {folder / subdirectory / path.name for folder in (base, derived_batch)}
        CHECK(path in candidates, "Artifact escapes the certified module directories")
        CHECK(A.file_digest(path) == record["digest"], "Sparse artifact digest differs: " + str(path))
        return path
    return resolve


def vm_image_home_scope(result, out):
    original = Path(result["base_batch"])
    base = read(original / "summary.json")
    summary = read(out / "summary.json")
    props = base["properties"]
    CHECK(props == summary["properties"] and Path(props["vm_profile"]["java_home"]).resolve() == original,
          "Sparse refresh must preserve the verified original VM profile and home")
    CHECK(artifact(original / "summary.json") == result["accepted_base"]["summary"] and
          artifact(out / "summary.json") == result["derivative"], "Properties provenance changed")
    records = [props["index"], *[u[k] for u in props["units"] for k in ("assembly","object")]]
    for rec in records:
        checked(rec, original / "properties")
    return dict(scope="original_VM_home_and_all_Properties_inputs_retained",
                vm_image_home=str(original), sparse_manifest_directory=str(out),
                base_summary=result["accepted_base"]["summary"], derived_summary=result["derivative"],
                vm_profile_sha256=hashlib.sha256(json.dumps(props["vm_profile"],sort_keys=True,
                    separators=(",",":"),ensure_ascii=True).encode()).hexdigest(), original_artifacts=records,
                regenerated_properties=False)


def locked_base(batch, plan, summary_sha, verification_sha):
    CHECK(batch.is_relative_to(ART) and plan.is_relative_to(ART), "Batch and plan must be under .boom")
    bs, bv = artifact(batch / "summary.json"), artifact(batch / "verification.json")
    CHECK(bs["digest"]["sha256"] == summary_sha and bv["digest"]["sha256"] == verification_sha,
          "Base batch or its accepted verification changed")
    b, v, p = read(Path(bs["path"])), read(Path(bv["path"])), read(plan / "summary.json")
    CHECK(b["schema"] == 23 and b["frames"]["abi"] == 3 and v.get("verified") and
          all(v[k]["verified"] for k in ("unsafe_fields", "unsafe_memory", "frames")) and
          b["unsafe_fields"]["abi"] == 1 and b["unsafe_fields"]["cookie_tag"] == U.TAGS[1] and
          b["input_fingerprint"] == p["input_fingerprint"], "Expected verified source frame ABI3 and UFMP ABI1")
    return b, p, dict(summary=bs, verification=bv, plan=artifact(plan / "summary.json"))


def reconstruct(batch, plan, base, source):
    """Read class order, native declaration and field address maps independently."""
    p = source["artifacts"]
    classes = [json.loads(row) for row in checked(p["classes"], plan).open(encoding="utf-8")]
    CHECK(all(c["id"] == i for i, c in enumerate(classes)), "Original classes reordered")
    owner, = [c for c in classes if c["name"] == U.OWNER and c["origin"]["loader"] == "bootstrap"]
    native_ids = set(owner["method_ids"])
    inventory = {}
    # Hash every record in the original method inventory, retain only Unsafe.
    methods = checked(p["methods"], plan)
    with methods.open("rb") as stream:
        for i, line in enumerate(stream):
            if i in native_ids:
                m = json.loads(line)
                CHECK(m["id"] == i and m["class_id"] == owner["id"], "Stale source method binding")
                inventory[i] = (m["class_id"], m["symbol"]["name"], m["symbol"]["descriptor"],
                                m["class_sha256"], m["code_sha256"], 0, 0, 0, m["access"])
    owner, natives = U.source_contract(classes, inventory)
    original = base["frames"]["original_system_catalog"]
    catalog = checked(original, ART)
    class_root = (catalog.parent / "image").resolve()
    class_file = (class_root / owner["origin"]["jar_entry"]).resolve()
    CHECK(class_file.is_relative_to(class_root), "Invalid original java.base class path")
    raw = class_file.read_bytes()
    CHECK(hashlib.sha256(raw).hexdigest() == owner["origin"]["sha256"], "Original Unsafe class changed")
    frames = script("verify-batch-frames")
    name, actual = frames.original_methods(raw)
    native = natives[0]
    CHECK(name == U.OWNER and len([m for m in actual if (m["name"], m["descriptor"], m["access"], m["code"]) ==
              (native["name"], native["descriptor"], native["access"], None)]) == 1,
          "Locked original objectFieldOffset1 declaration differs")
    info = base["runtime_metadata"]
    with zipfile.ZipFile(checked(info["index"], batch / "runtime-metadata")) as z:
        maps = [json.loads(line) for line in z.open("fields.jsonl")]
    shape = base["string_literals"]["source_layout"]
    fields, arena, ranges = U.model(classes, maps, shape["field_maps"], info["type_capacity"])
    originals = base["unsafe_fields"]
    CHECK(len(fields) == info["field_capacity"] == originals["declared_fields"] and
          0 < len(fields) <= 0xFFFFFF and len(maps) == info["provided_field_maps"] and
          len(ranges) == originals["type_capacity"] and len(arena) == originals["name_units"] and
          0 < len(ranges) <= 0x100000 and 0 < len(arena) <= 0x1000000 and
          originals["context_bytes"] == 32 and originals["record_bytes"] == 64 and
          originals["pool_bytes"] == 128 and originals["page_fields"] == 1024 and
          originals["pages"] == (len(fields) + 1023) // 1024 and
          originals["instance_fields"] == sum(not row["access"] & 8 for row in fields) and
          originals["address_maps"] == sum(row["address_map"] is not None for row in fields) and
          originals["native_methods"] == 1 and originals["class_id"] == owner["id"] and
          originals["class_sha256"] == owner["origin"]["sha256"] and
          originals["source_native_declarations"] == sum(bool(m["access"] & 0x100) for m in actual),
          "Unsafe field source inventory differs")
    inputs = (fields, arena, ranges, owner["id"], shape, native["method"])
    old, u1 = U.bodies(*inputs, 1)
    new, u2 = U.bodies(*inputs, 2)
    CHECK(u1 == u2 and [i for i, (a, b) in enumerate(zip(old, new)) if a != b] == [u1] and
          len(old) == len(new) == len(originals["units"]), "Source partition or changed units differ")
    native["assembly_unit"] = u1
    with zipfile.ZipFile(checked(originals["index"], batch / "unsafe-fields")) as z:
        CHECK(z.namelist() == ["methods.jsonl", "fields.jsonl", "names.json", "ranges.json"] and
              [json.loads(line) for line in z.open("methods.jsonl")] == natives and
              json.loads(z.read("names.json")) == arena and json.loads(z.read("ranges.json")) == ranges,
              "Original source index or ranges differ")
        with z.open("fields.jsonl") as stream:
            for field in fields:
                CHECK(json.loads(stream.readline()) == field, "Original Field64 index differs")
            CHECK(not stream.read(1), "Extra field rows")
    selected = None
    for i, unit in enumerate(originals["units"]):
        CHECK(unit["id"] == i and not unit["assembler_diagnostic"] and unit["body_bytes"] == len(old[i]),
              "Base unit partition differs")
        asm = checked(unit["assembly"], batch / "unsafe-fields")
        checked(unit["object"], batch / "unsafe-fields")
        text = asm.read_bytes().decode("utf-8")
        prefix, sep, body = text.partition(".code\n")
        CHECK(sep and body == old[i] + "\nEND\n", "Base MASM differs from source-derived fields")
        if i == u1:
            selected = (prefix + sep + new[i] + "\nEND\n").encode()
    CHECK(selected, "Missing changed pool unit")
    return u1, selected, inventory, dict(classes=p["classes"], methods=p["methods"], runtime_field_maps=info["index"],
                              field_index=originals["index"], original_Unsafe=artifact(class_file),
                              original_system_catalog=original)


def normalized_coff(path, abi):
    """Normalize the timestamp, CodeView object path and two ABI header members."""
    data = bytearray(path.read_bytes())
    machine, sections, _, sym_at, sym_count, opt, _ = struct.unpack_from("<HHIIIHH", data)
    CHECK(machine == 0x8664 and sections and opt == 0, "Expected AMD64 COFF")
    strings = sym_at + 18 * sym_count
    sym = 0
    matches = []
    debug_aux = []
    while sym < sym_count:
        at = sym_at + sym * 18
        name = bytes(data[at:at + 8])
        offset, section, _, storage, aux = struct.unpack_from("<IhHBB", data, at + 8)
        if name[:4] == b"\0" * 4:
            start = strings + int.from_bytes(name[4:], "little")
            name = bytes(data[start:data.index(0, start)])
        if name.rstrip(b"\0") == b"boom_java_unsafe_field_pool" and storage == 2 and section > 0:
            CHECK(section <= sections, "Invalid UFMP COFF section")
            size, raw = struct.unpack_from("<II", data, 20 + (section - 1) * 40 + 16)
            CHECK(offset + 128 <= size, "Pool escapes COFF section")
            matches.append(raw + offset)
        if name == b".debug$S" and storage == 3 and section > 0 and aux == 1:
            debug_aux.append((section, at + 18))
        sym += aux + 1
    CHECK(len(matches) == 1, "Missing unique physical UFMP128 pool")
    at = matches[0]
    CHECK(struct.unpack_from("<II", data, at) == (0x55464D50, abi) and
          struct.unpack_from("<QQ", data, at + 112) == (U.TAGS[abi], 0),
          "COFF pool magic, ABI, tag or reserved field differs")
    data[4:8] = bytes(4)
    data[at + 4:at + 8] = bytes(4)
    data[at + 112:at + 120] = bytes(8)
    # ml64 records the absolute /Fo path even with debug switches off. Preserve
    # every other COFF byte, including compiler identity, relocations and symbols.
    CHECK(len(debug_aux) == 1, "Missing standard ml64 CodeView section")
    section, aux = debug_aux[0]
    sh = 20 + (section - 1) * 40
    size, start, reloc, lines = struct.unpack_from("<IIII", data, sh + 16)
    CHECK(data[sh:sh + 8] == b".debug$S" and start + size == sym_at and not reloc and not lines and
          struct.unpack_from("<I", data, aux)[0] == size, "Unexpected CodeView layout")
    sig, subsection, length, namelen, kind, zero = struct.unpack_from("<IIIHHI", data, start)
    CHECK((sig, subsection, kind, zero) == (4, 0xf1, 0x1101, 0) and
          7 <= namelen <= length - 2 and length <= size - 12 and size - 12 - length <= 3,
          "Unexpected ml64 object-path record")
    endname = start + 14 + namelen
    CHECK(data[endname - 1] == 0 and 0 not in data[start + 20:endname - 1] and
          not any(data[start + 12 + length:sym_at]), "Invalid CodeView object name/alignment")
    data[8:12] = bytes(4)
    data[sh + 16:sh + 20] = bytes(4)
    data[aux:aux + 4] = bytes(4)
    return data[:start], data[endname:start + 12 + length], data[sym_at:]


def derived(base, index, asm, obj, kernel_hash, registry=None, initialization=None):
    result = deepcopy(base)
    fields = result["unsafe_fields"]
    fields.update(abi=2, cookie_tag=U.TAGS[2], **U.SLOT)
    unit = fields["units"][index]
    unit.update(assembly=asm, object=obj, assembler_cache=None)
    old = base["unsafe_fields"]["kernel_sha256"][KERNEL]
    CHECK(base["unsafe_memory"]["kernel_sha256"][KERNEL] == old, "Base field and memory kernels differ")
    for family in ("unsafe_fields", "unsafe_memory"):
        result[family]["kernel_sha256"][KERNEL] = kernel_hash
    if registry:
        result["unsafe_memory"]["kernel_sha256"]["native/runtime/thread_registry.asm"] = registry["current"]["digest"]["sha256"]
    if initialization:
        dependency = "native/runtime/classes32.asm"
        for family in ("frames", "class_lookup"):
            result[family]["kernel_sha256"][dependency] = initialization["sources"][dependency]["current"]["digest"]["sha256"]
    return result


def record_at(path, final):
    return dict(path=str(final), digest=A.file_digest(path))


def write(out, name, value):
    (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def verify_field_scope(base, summary, inventory, batch, plan, out):
    """Run the normal field verifier against actual upstream symbol definitions."""
    resolve = sparse_artifacts(batch, out)
    available = set()
    for family in ("runtime_metadata", "string_literals", "class_literals", "unsafe_bootstrap"):
        # Same two Windows wait primitives admitted by the string-literal verifier.
        imports = {"WaitOnAddress", "WakeByAddressAll"} if family == "string_literals" else set()
        for unit in base[family]["units"]:
            obj = resolve(out, unit["object"], family.replace("_", "-"))
            definitions, _ = A.coff_symbols(obj, imports)
            available.update(definitions)
    verified, defined, dependencies, natives = U.verify(out, summary, plan, inventory, available,
                                                       resolve, A.coff_symbols, A.file_digest)
    CHECK(verified["verified"] and len(natives) == 1, "Field verification failed")
    return dict(scope="UFMP_ABI2_source_index_MASM_COFF_and_providing_symbols",
                summary=artifact(out / "summary.json"), field_verification=verified,
                defined=len(defined), external_symbols=len(dependencies), full_batch_reverified=False)


def process(batch, plan, out, stage, assembler, summary_sha, verification_sha, build, check_fields=False,
            old_registry=None, runtime=None, previous_runtime=None, class_regression=None):
    b, p, inputs = locked_base(batch, plan, summary_sha, verification_sha)
    index, expected_asm, inventory, sources = reconstruct(batch, plan, b, p)
    before = b["unsafe_fields"]["units"][index]
    asm_tool = artifact(assembler)
    old_build = before.get("assembler_cache")
    if old_build:
        CHECK(asm_tool["digest"]["sha256"] == old_build["assembler_sha256"], "Assembler differs from base")
    CHECK((old_registry is None) == (runtime is None), "Thread-counter refresh needs both source and tested runtime")
    registry = None
    if old_registry is not None:
        registry = script("unsafe-thread-counter-compatibility").prove(ROOT, ART, old_registry, runtime,
                                                                       assembler, b, artifact)
    CHECK((previous_runtime is None) == (class_regression is None), "Class dependency refresh needs previous runtime and regression")
    initialization = None
    if previous_runtime is not None:
        CHECK(registry is not None, "Class initialization refresh requires the checked combined runtime")
        initialization = script("unsafe-batch-class-init-compatibility").prove(
            ROOT, ART, b, old_registry.parent, previous_runtime, runtime, class_regression, artifact, script)
    name = Path(before["assembly"]["path"]).name
    directory = stage / "unsafe-fields"
    asm = directory / name
    obj = asm.with_suffix(".obj")
    asm_final = out / "unsafe-fields" / name
    if build:
        directory.mkdir()
        asm.write_bytes(expected_asm)
        env = {k: v for k, v in os.environ.items() if k.upper() not in ("ML", "_ML_")}
        subprocess.run([str(assembler), "/nologo", "/c", "/Fo" + str(obj), str(asm)],
                       cwd=directory, env=env, check=True, timeout=180)
    CHECK(asm.read_bytes() == expected_asm, "Derived MASM differs from independently regenerated ABI2")
    old_obj = Path(before["object"]["path"])
    CHECK(normalized_coff(old_obj, 1) == normalized_coff(obj, 2), "COFF changed beyond the two UFMP header values")
    after_asm = record_at(asm, asm_final)
    after_obj = record_at(obj, asm_final.with_suffix(".obj"))
    current_kernel = artifact(ROOT / KERNEL)
    summary = derived(b, index, after_asm, after_obj, current_kernel["digest"]["sha256"], registry, initialization)
    # The checked bytes prove the same compiler/shards, source field map, native
    # code/relocations and receiver layouts used by this accepted base. Keeping
    # all original paths permits selection without copying the Java batch.
    if build:
        write(stage, "summary.json", summary)
    CHECK(read(stage / "summary.json") == summary, "Sparse summary contains unrelated changes")
    result = dict(schema=1, scope="verified_original_batch_with_only_UFMP_ABI2_pool_replaced",
                  base_batch=str(batch), plan=str(plan), accepted_base=inputs, source_inputs=sources,
                  input_fingerprint=b["input_fingerprint"], ir_identity=b["ir_identity"],
                  derivative=record_at(stage / "summary.json", out / "summary.json"),
                  replacements=[dict(unit=index, original_assembly=before["assembly"], original_object=before["object"],
                                     assembly=after_asm, object=after_obj)],
                  kernel=dict(previous_sha256=b["unsafe_fields"]["kernel_sha256"][KERNEL], current=current_kernel),
                  assembler=asm_tool, native_field_index_unchanged=True, original_Java_units_recompiled=0,
                  source_metadata_reconstructed=True, all_other_summary_fields_equal=True,
                  full_batch_reverified=False, profile_rebound=False, executed=False, game_started=False)
    if registry:
        result.update(schema=2, scope="verified_UFMP_ABI2_pool_and_thread_counter_kernel_dependency_refresh",
                      thread_counter=registry)
    if initialization:
        result.update(schema=3, scope="verified_UFMP_ABI2_thread_counter_and_class_initialization_dependency_refresh",
                      class_initialization=initialization)
    if build:
        write(stage, "unsafe-field-derivation.json", result)
    else:
        CHECK(read(stage / "unsafe-field-derivation.json") == result, "Sparse proof differs from its source")
        if check_fields:
            scope = verify_field_scope(b, summary, inventory, batch, plan, out)
            target = out / "unsafe-field-verification.json"
            if target.exists():
                CHECK(read(target) == scope, "Existing field verification differs")
            else:
                with tempfile.TemporaryDirectory(dir=out) as tmp:
                    write(Path(tmp), target.name, scope)
                    os.link(Path(tmp) / target.name, target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    make = commands.add_parser("build")
    check = commands.add_parser("verify")
    fields = commands.add_parser("verify-fields", help="Verify the complete field module and its supplying COFF symbols")
    full = commands.add_parser("verify-full", help="Run the original verifier across the entire sparse batch")
    full.add_argument("--ir", type=Path, required=True)
    for cmd in (make, check, fields, full):
        cmd.add_argument("--directory", type=Path, required=True)
        cmd.add_argument("--base-summary-sha256", required=True)
        cmd.add_argument("--base-verification-sha256", required=True)
    for flag in ("--batch", "--plan", "--assembler"):
        make.add_argument(flag, type=Path, required=True)
    make.add_argument("--thread-registry-before", type=Path)
    make.add_argument("--tested-runtime", type=Path)
    make.add_argument("--class-init-previous-runtime", type=Path)
    make.add_argument("--class-init-regression", type=Path)
    a = parser.parse_args()
    out = a.directory.resolve()
    CHECK(out.is_relative_to(ART) and out != ART, "Write derivations only inside project .boom")
    if a.action == "build":
        CHECK(not out.exists(), "Output already exists")
        out.parent.mkdir(parents=True, exist_ok=True)
        # Publish both source identity and objects atomically; never edit the source batch.
        with tempfile.TemporaryDirectory(prefix="stage-ufmp-", dir=out.parent) as tmp:
            stage = Path(tmp) / "derived"
            stage.mkdir()
            result = process(a.batch.resolve(), a.plan.resolve(), out, stage, a.assembler.resolve(),
                             a.base_summary_sha256, a.base_verification_sha256, True,
                             old_registry=a.thread_registry_before.resolve() if a.thread_registry_before else None,
                             runtime=a.tested_runtime.resolve() if a.tested_runtime else None,
                             previous_runtime=a.class_init_previous_runtime.resolve() if a.class_init_previous_runtime else None,
                             class_regression=a.class_init_regression.resolve() if a.class_init_regression else None)
            stage.rename(out)
    else:
        r = read(out / "unsafe-field-derivation.json")
        registry = r.get("thread_counter")
        initialization = r.get("class_initialization")
        result = process(Path(r["base_batch"]).resolve(), Path(r["plan"]).resolve(), out, out,
                         Path(r["assembler"]["path"]), a.base_summary_sha256, a.base_verification_sha256, False,
                         check_fields=a.action == "verify-fields",
                         old_registry=Path(registry["previous"]["path"]).resolve() if registry else None,
                         runtime=Path(registry["runtime_manifest"]["path"]).resolve().parent if registry else None,
                         previous_runtime=Path(initialization["previous_manifest"]["path"]).resolve().parent if initialization else None,
                         class_regression=Path(initialization["regression"]["path"]).resolve() if initialization else None)
        if a.action == "verify-full":
            # Load an isolated verifier instance. Its only adaptation is content-
            # checked artifact location; every normal full verification check runs.
            original = script("verify-batch-assembly")
            scope = vm_image_home_scope(result, out)
            original.artifact = sparse_artifacts(Path(result["base_batch"]), out)
            original.artifact.verified_original_vm_image_home = Path(scope["vm_image_home"])
            verified = original.verify(out, Path(result["plan"]), a.ir.resolve())
            CHECK(verified["verified"], "Full verification failed")
            verified["sparse_original_vm_image_home"] = scope
            target = out / "verification.json"
            if target.exists():
                CHECK(read(target) == verified, "A different full verification already exists")
            else:
                with tempfile.TemporaryDirectory(dir=out) as tmp:
                    write(Path(tmp), "verification.json", verified)
                    os.link(Path(tmp) / "verification.json", target)
            print(out / "verification.json")
            return
    print(json.dumps(dict(directory=str(out), summary_sha256=result["derivative"]["digest"]["sha256"],
                          replacement_unit=result["replacements"][0]["unit"], full_batch_reverified=False)))


if __name__ == "__main__":
    main()
