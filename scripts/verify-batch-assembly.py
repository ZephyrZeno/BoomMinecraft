"""Verify batch artifact coverage and real AMD64 COFF symbols; no guest execution."""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile


def check(value, message):
    if not value:
        raise ValueError(message)


def file_digest(path):
    sha1, sha256, size = hashlib.sha1(), hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        while block := stream.read(1024*1024):
            sha1.update(block)
            sha256.update(block)
            size += len(block)
    return dict(size=size, sha1=sha1.hexdigest(), sha256=sha256.hexdigest())


def artifact(root, metadata, subdirectory=""):
    path = root/subdirectory/Path(metadata["path"]).name
    check(file_digest(path) == metadata["digest"], f"Artifact changed: {path}")
    return path


def coff_symbols(path, allowed_foreign=frozenset()):
    data = Path(path).read_bytes()
    check(len(data) >= 20, "Truncated COFF header")
    machine, sections, _, offset, count, optional, _ = struct.unpack_from("<HHIIIHH", data)
    check(machine == 0x8664 and sections > 0 and optional == 0, "Expected AMD64 COFF object")
    check(offset >= 20+sections*40 and offset+count*18+4 <= len(data), "Invalid COFF symbol table")
    strings = offset+count*18
    string_size = struct.unpack_from("<I", data, strings)[0]
    check(string_size >= 4 and strings+string_size <= len(data), "Invalid COFF string table")
    defined, undefined = set(), set()
    index = 0
    while index < count:
        at = offset+index*18
        raw, _, section, _, storage, auxiliary = struct.unpack_from("<8sIhHBB", data, at)
        if raw[:4] == b"\0"*4:
            name_offset = strings+struct.unpack_from("<I", raw, 4)[0]
            check(strings+4 <= name_offset < strings+string_size, "Invalid COFF symbol name")
            end = data.find(b"\0", name_offset, strings+string_size)
            check(end != -1, "Unterminated COFF symbol name")
            name = data[name_offset:end].decode("ascii")
        else:
            name = raw.rstrip(b"\0").decode("ascii")
        check(section <= sections and index+1+auxiliary <= count, "Invalid COFF symbol metadata")
        if storage == 2:
            if section > 0: defined.add(name)
            elif section == 0: undefined.add(name)
        index += 1+auxiliary
    # __imp_boom_* is the Windows IAT address of our own runtime export.
    # Foreign imports still require an explicit caller-supplied allowlist.
    check(all(name.startswith(("boom_","__imp_boom_")) or name in allowed_foreign for name in undefined), "Unexpected foreign runtime symbol")
    return defined, undefined


def verify(root, plan, ir=None):
    root, plan = Path(root), Path(plan)
    summary = json.loads((root/"summary.json").read_text(encoding="utf-8"))
    source = json.loads((plan/"summary.json").read_text(encoding="utf-8"))
    check(summary["mode"] == "typed_assembly_candidates_unlinked", "Unexpected batch mode")
    check(summary["schema"] in range(1,24), "Unsupported batch schema")
    check(summary["input_fingerprint"] == source["input_fingerprint"], "Batch source identity differs")
    for flag in ("runtime_abi_verified", "module_access_verified", "linked", "automatic_memory_reclamation",
                 "game_started", "world_created", "full_game_ready"):
        check(summary[flag] is False, f"Unlinked batch incorrectly claims {flag}")
    inventory = []
    method_path = plan/"methods.jsonl"
    check(file_digest(method_path) == source["artifacts"]["methods"]["digest"], "Source method plan changed")
    with method_path.open(encoding="utf-8") as stream:
        for line in stream:
            method = json.loads(line)
            check(method["id"] == len(inventory), "Invalid source method identity")
            inventory.append((method["class_id"], method["symbol"]["name"], method["symbol"]["descriptor"],
                              method["class_sha256"], method["code_sha256"], method["code_bytes"],
                              method["max_locals"], method["max_stack"], method['access']))
    dispatch_verifier, dispatch_requests = None, None
    frame_verifier=None;emitted_frames=set()
    if summary['schema']>=23:
        spec=importlib.util.spec_from_file_location('source_frame_verifier',Path(__file__).with_name('verify-batch-frames.py'))
        frame_verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(frame_verifier)
        spec=importlib.util.spec_from_file_location('frame_source_procedures',Path(__file__).with_name('batch-source.py'))
        frame_sources=importlib.util.module_from_spec(spec);spec.loader.exec_module(frame_sources)
    if summary['schema'] >= 6:
        spec = importlib.util.spec_from_file_location('dispatch_verifier', Path(__file__).with_name('verify-batch-dispatch.py'))
        dispatch_verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(dispatch_verifier)
        dispatch_requests = dispatch_verifier.Requests(enable_array_clones=summary['schema']>=7,enable_classes=summary['schema']>=10,enable_concat=summary['schema']>=14)
    counts, classes, seen = Counter(), set(), set()
    assembled = 0
    declared_units, assembled_units = 0, 0
    total_defined, total_undefined = 0, 0
    global_defined, global_undefined = set(), set()
    emitted_initializers = set()
    for shard in summary["shards"]:
        path = artifact(root, shard["zip"], "shards")
        if summary["schema"] >= 2:
            units = shard["units"]
        else:
            units = [dict(id=0, assembly=shard["assembly"], object=shard["object"],
                          assembler_diagnostic=shard["assembler_diagnostic"])] if shard["assembly"] else []
        expected_symbols = defaultdict(set)
        expected_frames = defaultdict(list)
        local = Counter()
        with zipfile.ZipFile(path) as bundle:
            for filename in bundle.namelist():
                unit = json.loads(bundle.read(filename))
                class_id = unit["class_id"]
                check(class_id not in classes, "Duplicate batch class")
                classes.add(class_id)
                for method in unit["methods"]:
                    method_id = method["id"]
                    check(method_id not in seen and 0 <= method_id < len(inventory), "Duplicate/invalid batch method")
                    seen.add(method_id)
                    owner, name, desc, class_sha, code_sha, code_length, max_locals, max_stack, access = inventory[method_id]
                    check((owner, name, desc, class_sha, code_sha) ==
                          (class_id, method["name"], method["descriptor"], unit["source_sha256"], method["code_sha256"]),
                          "Batch method differs from source inventory")
                    if code_sha is None:
                        check(method["stage"] == "declaration" and not method["assembly_emitted"],
                              "Native/abstract declaration was presented as compiled code")
                        if summary["schema"] >= 2:
                            check(method["assembly_unit"] is None, "Declaration has an assembly unit")
                        local["declarations"] += 1
                        continue
                    local["java_methods"] += 1
                    local["operand_verified"] += method["operand_verified"]
                    local["assembly_emitted"] += method["assembly_emitted"]
                    local["failed_methods"] += method["diagnostic"] is not None
                    check(method["assembly_emitted"] <= method["operand_verified"], "Unverified operands were emitted")
                    if method["assembly_emitted"]:
                        if dispatch_requests is not None: dispatch_requests.emitted.add(method_id)
                        if method['name']=='<clinit>': emitted_initializers.add(method_id)
                        check(method["stage"] == "assembly_emitted_unlinked" and method["diagnostic"] is None,
                              "Generated method has an invalid stage")
                        unit_id = method.get("assembly_unit", 0)
                        check(isinstance(unit_id, int) and 0 <= unit_id < len(units), "Invalid method assembly unit")
                        expected_symbols[unit_id].update((f"boom_m{method_id}", f"boom_m{method_id}_body"))
                    else:
                        check(method["diagnostic"] is not None, "Failed method lacks a diagnostic")
                    maps = method["references"]
                    local["reference_maps"] += len(maps)
                    previous = -1
                    for frame in maps:
                        check(previous < frame["pc"] < code_length, "Invalid reference-map PC")
                        previous = frame["pc"]
                        for slots, bound in ((frame["local_slots"], max_locals), (frame["operand_values"], max_stack)):
                            check(slots == sorted(set(slots)) and all(0 <= n < bound for n in slots),
                                  "Invalid typed reference-map slot")
                    for binding in method["bindings"]:
                        check(binding["implemented"] is False, "Binding declaration falsely claims an implementation")
                        if dispatch_requests is not None and method['assembly_emitted']:
                            dispatch_requests.observe(class_id, class_sha, method_id, binding)
                    if frame_verifier is not None and method['assembly_emitted']:
                        emitted_frames.add(method_id)
                        expected_frames[method['assembly_unit']].append((method_id,max_locals,max_stack,tuple(f['pc'] for f in maps)))
        for key in ("declarations", "java_methods", "operand_verified", "assembly_emitted", "failed_methods", "reference_maps"):
            check(local[key] == shard["counts"][key], f"Batch shard coverage differs: {key}")
            counts[key] += local[key]
        shard_assembled = True
        declared_units += len(units)
        check(set(expected_symbols) == set(range(len(units))), "Assembly units do not match generated methods")
        for unit_id, unit in enumerate(units):
            check(unit["id"] == unit_id, "Noncontiguous assembly unit identity")
            assembly = artifact(root, unit["assembly"], "shards")
            if frame_verifier is not None:
                frame_text=assembly.read_text(encoding='utf-8');spans=frame_sources.procedure_spans(frame_text)
                for i,locals_,stack_,pcs in expected_frames[unit_id]:
                    start,end=spans[f'boom_m{i}_body']
                    frame_verifier.java_frame(frame_text[start:end],i,locals_,stack_,pcs)
            if summary["schema"] >= 2:
                with assembly.open("rb") as stream:
                    header = 0
                    for line in stream:
                        header += len(line)
                        if line == b".code\n": break
                    else: raise ValueError("Missing assembly module code marker")
                    stream.seek(-5, 2)
                    check(stream.read() == b"\nEND\n", "Invalid assembly module trailer")
                body_bytes = unit["assembly"]["digest"]["size"]-header-5
                check(body_bytes == unit["body_bytes"], "Assembly body byte count differs")
                check(body_bytes <= summary["assembly_body_budget_bytes"] or len(expected_symbols[unit_id]) == 2,
                      "Oversized assembly unit contains multiple methods")
            check(unit["object"] is not None, "Assembly unit has no successful COFF object")
            check(unit["assembler_diagnostic"] is None, "Object has an assembler failure")
            obj = artifact(root, unit["object"], "shards")
            defined, undefined = coff_symbols(obj)
            method_definitions = {name for name in defined if re.fullmatch(r"boom_m\d+(?:_body)?", name)}
            check(expected_symbols[unit_id] == method_definitions, "Generated methods differ from COFF symbols")
            check(not any(name.startswith("boom_batch_") for name in defined),
                  "Unresolved runtime contracts were defined as placeholder functions")
            total_defined += len(defined)
            total_undefined += len(undefined)
            global_defined.update(defined)
            global_undefined.update(undefined)
            assembled_units += 1
        if units and shard_assembled: assembled += 1
    check(len(classes) == summary["classes"] == source["classes"], "Batch class coverage differs")
    check(seen == set(range(source["methods"])), "Batch method coverage differs")
    for key, value in counts.items(): check(value == summary["counts"][key], f"Batch total differs: {key}")
    check(assembled == summary["assembled_shards"], "Assembled shard total differs")
    check(summary["assembler_failures"] == 0, "Batch has assembler failures")
    if summary["schema"] >= 2:
        check(declared_units == summary["assembly_units"] and assembled_units == summary["assembled_units"],
              "Assembly unit coverage differs")
    artifact(root, summary["layouts"])
    artifact(root, summary["array_types"])
    artifact(root, summary["numeric_kernel"])
    check(summary["numeric_kernel_object"] is not None, "Missing assembled shared numeric kernel")
    if summary["numeric_kernel_object"]:
        defined, undefined = coff_symbols(artifact(root, summary["numeric_kernel_object"]))
        check({"boom_frem32", "boom_frem64"} <= defined and not undefined, "Shared arithmetic kernel is not self-contained")
        global_defined.update(defined)
        global_undefined.update(undefined)
    literal_result = None
    static_inputs = {} if summary['schema'] >= 5 else None
    if summary["schema"] >= 3:
        check(ir is not None, "Schema 3 requires source IR for literal verification")
        spec = importlib.util.spec_from_file_location("literal_module_verifier", Path(__file__).with_name("verify-string-literal-module.py"))
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        literal_result, defined, undefined = verifier.verify(root, summary, ir, artifact, coff_symbols, file_digest, static_inputs,
            dispatch_requests.constants if dispatch_requests is not None else None)
        check(not global_defined & defined, "Literal data conflicts with Java function definitions")
        global_defined.update(defined)
        global_undefined.update(undefined)
    metadata_result = None
    if summary["schema"] >= 4:
        spec = importlib.util.spec_from_file_location("runtime_metadata_verifier", Path(__file__).with_name("verify-batch-metadata.py"))
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        metadata_result, defined, undefined = verifier.verify(root, summary, plan, artifact, coff_symbols, file_digest)
        check(not global_defined & defined, "Runtime metadata conflicts with existing source definitions")
        global_defined.update(defined)
        global_undefined.update(undefined)
    class_state_result = None
    if summary['schema'] >= 5:
        spec = importlib.util.spec_from_file_location('class_state_verifier',Path(__file__).with_name('verify-batch-class-state.py'))
        verifier = importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        class_state_result,defined,undefined=verifier.verify(root,summary,plan,static_inputs,emitted_initializers,artifact,coff_symbols,file_digest)
        check(not global_defined & defined,'Class state conflicts with existing definitions')
        global_defined.update(defined);global_undefined.update(undefined)
    system_result, provided_natives = None, frozenset()
    if summary['schema']>=8:
        spec=importlib.util.spec_from_file_location('system_verifier',Path(__file__).with_name('verify-batch-system.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        system_result,defined,undefined,provided_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'System natives conflict with existing source definitions')
        global_defined.update(defined);global_undefined.update(undefined)
    class_result=None
    if summary['schema']>=10:
        spec=importlib.util.spec_from_file_location('normal_Class_verifier',Path(__file__).with_name('verify-batch-classes.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        class_result,defined,undefined,class_natives=verifier.verify(root,summary,plan,inventory,dispatch_requests,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Normal Class definitions conflict with existing modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|class_natives
    class_bootstrap_result=None
    if summary['schema']>=15:
        spec=importlib.util.spec_from_file_location('normal_Class_bootstrap_verifier',Path(__file__).with_name('verify-batch-class-bootstrap.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        class_bootstrap_result,defined,undefined,bootstrap_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Class bootstrap definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|bootstrap_natives
    unsafe_result=None
    if summary['schema']>=16:
        spec=importlib.util.spec_from_file_location('normal_Unsafe_verifier',Path(__file__).with_name('verify-batch-unsafe.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        unsafe_result,defined,undefined,unsafe_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Unsafe definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|unsafe_natives
    vm_result=None
    if summary['schema']>=17:
        spec=importlib.util.spec_from_file_location('normal_VM_verifier',Path(__file__).with_name('verify-batch-vm.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        vm_result,defined,undefined,vm_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'VM native definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|vm_natives
    resources_result=None
    if summary['schema']>=18:
        spec=importlib.util.spec_from_file_location('normal_Runtime_resource_verifier',Path(__file__).with_name('verify-batch-runtime-resources.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        resources_result,defined,undefined,resource_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Runtime resource definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|resource_natives
    bitcast_result=None
    if summary['schema']>=19:
        spec=importlib.util.spec_from_file_location('normal_bitcast_verifier',Path(__file__).with_name('verify-batch-bitcasts.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        bitcast_result,defined,undefined,bitcast_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Bitcast native definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|bitcast_natives
    unsafe_fields_result=None
    if summary['schema']>=20:
        spec=importlib.util.spec_from_file_location('normal_Unsafe_field_verifier',Path(__file__).with_name('verify-batch-unsafe-fields.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        unsafe_fields_result,defined,undefined,field_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Unsafe field definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|field_natives
    frames_result=None
    if frame_verifier is not None:
        frames_result,defined,undefined,frame_natives=frame_verifier.verify(root,summary,plan,inventory,emitted_frames,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Frame source definitions conflict')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|frame_natives
    class_lookup_result=None
    if summary['schema']>=22:
        spec=importlib.util.spec_from_file_location('normal_Class_lookup_verifier',Path(__file__).with_name('verify-batch-class-lookup.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        class_lookup_result,defined,undefined,lookup_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Class lookup definitions conflict')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives|lookup_natives)
    unsafe_memory_result=None
    if summary['schema']>=21:
        spec=importlib.util.spec_from_file_location('normal_Unsafe_memory_verifier',Path(__file__).with_name('verify-batch-unsafe-memory.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        unsafe_memory_result,defined,undefined,memory_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Unsafe memory definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|memory_natives
    intern_result=None
    if summary['schema']>=12:
        spec=importlib.util.spec_from_file_location('normal_intern_verifier',Path(__file__).with_name('verify-batch-string-intern.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        intern_result,defined,undefined,intern_natives=verifier.verify(root,summary,plan,inventory,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Intern definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|intern_natives
    properties_result=None
    if summary['schema']>=13:
        spec=importlib.util.spec_from_file_location('normal_properties_verifier',Path(__file__).with_name('verify-batch-properties.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        properties_result,defined,undefined,property_natives=verifier.verify(root,summary,plan,inventory,static_inputs,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Property definitions conflict with source modules')
        global_defined.update(defined);global_undefined.update(undefined);provided_natives=frozenset(provided_natives)|property_natives
    concat_result=None
    if summary['schema']>=14:
        spec=importlib.util.spec_from_file_location('normal_concat_verifier',Path(__file__).with_name('verify-batch-concat.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        concat_result,defined,undefined=verifier.verify(root,summary,plan,inventory,dispatch_requests,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Concat expansion conflicts with source definitions')
        global_defined.update(defined);global_undefined.update(undefined)
    dispatch_result = None
    if dispatch_requests is not None:
        dispatch_result, defined, undefined = dispatch_verifier.verify(root, summary, plan, inventory, dispatch_requests, artifact, coff_symbols, file_digest,provided_natives)
        check(not global_defined & defined, 'Dispatch conflicts with existing source definitions')
        global_defined.update(defined); global_undefined.update(undefined)
    clone_result = None
    if summary['schema']>=7:
        spec=importlib.util.spec_from_file_location('clone_verifier',Path(__file__).with_name('verify-batch-array-clone.py'))
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        clone_result,defined,undefined=verifier.verify(root,summary,plan,inventory,dispatch_requests,global_defined,artifact,coff_symbols,file_digest)
        check(not global_defined&defined,'Clone adapters conflict with existing source definitions')
        global_defined.update(defined);global_undefined.update(undefined)
    unresolved = global_undefined-global_defined
    categories = Counter()
    for name in unresolved:
        if name.startswith("boom_batch_call_"):
            category = "call_adapters"
        elif name.startswith("boom_batch_literal_"):
            category = "literal_resolution"
        elif re.fullmatch(r"boom_m\d+", name):
            category = "method_implementations"
        else:
            category = "metadata_and_runtime_symbols"
        categories[category] += 1
    return dict(verified=True, scope="batch_artifact_coverage_reference_slots_and_AMD64_COFF_symbols_only",
                classes=len(classes), methods=len(seen), counts=dict(counts), assembled_shards=assembled,
                assembly_units=assembled_units,
                public_defined_symbols=total_defined, unresolved_symbol_references=total_undefined,
                unresolved_unique_symbols=len(unresolved), unresolved_categories=dict(categories),
                string_literals=literal_result,
                runtime_metadata=metadata_result,
                class_state=class_state_result,
                dispatch=dispatch_result,
                array_clone=clone_result,
                system_natives=system_result,
                class_literals=class_result,
                string_intern=intern_result,
                properties=properties_result,
                string_concat=concat_result,
                class_bootstrap=class_bootstrap_result,
                unsafe_bootstrap=unsafe_result,
                vm_registration=vm_result,
                runtime_resources=resources_result,
                bitcasts=bitcast_result,
                unsafe_fields=unsafe_fields_result,
                unsafe_memory=unsafe_memory_result,class_lookup=class_lookup_result,frames=frames_result,
                linkage_scope="symbol_closure_only_not_final_linker_or_runtime_validation",
                linked=False, runtime_abi_verified=False, game_started=False, world_created=False, full_game_ready=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ir", type=Path)
    args = parser.parse_args()
    result = verify(args.batch, args.plan, args.ir)
    if args.output: args.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
