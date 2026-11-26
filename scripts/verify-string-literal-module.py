"""Check source IR constants against canonical data, thunks and real COFF exports."""
import json
from pathlib import Path
import re
import zipfile


def check(value, message):
    if not value:
        raise ValueError(message)


def java_hash(units):
    result = 0
    for unit in units:
        check(isinstance(unit, int) and 0 <= unit <= 65535, "Invalid UTF16 unit")
        result = (result*31+unit) & 0xffffffff
    return result


def verify(root, batch, ir, artifact, coff_symbols, file_digest, static_inputs=None, dispatch_inputs=None):
    root, ir = Path(root), Path(ir)
    summary = batch["string_literals"]
    for flag in ("linked", "general_string_intern", "original_string_java_bodies_executed", "automatic_gc"):
        check(summary[flag] is False, "Literal metadata falsely claims full runtime support")
    check(summary["abi"] == 1 and summary["compact_strings"] is True
          and summary["entry_page_size"] == 256, "Invalid literal module ABI")
    ir_summary = json.loads((ir/"summary.json").read_text(encoding="utf-8"))
    check(ir_summary["identity"] == batch["ir_identity"]
          and ir_summary["input_fingerprint"] == batch["input_fingerprint"], "Literal source IR differs")
    check(file_digest(ir/"shards.jsonl") == ir_summary["index"]["digest"], "Literal source index changed")
    with zipfile.ZipFile(artifact(root, summary["index"], "string-literals")) as bundle:
        check(sorted(bundle.namelist()) == ["bindings.jsonl", "canonical.jsonl"], "Unexpected literal index")
        rows = [json.loads(line) for line in bundle.read("canonical.jsonl").splitlines()]
        aliases = [json.loads(line) for line in bundle.read("bindings.jsonl").splitlines()]
    canonical = []
    for row in rows:
        check(row["id"] == len(canonical), "Noncontiguous canonical identity")
        units = tuple(row["utf16"])
        check(len(units) <= 65535 and java_hash(units) == row["java_hash"], "Literal UTF16/hash differs")
        check(not canonical or canonical[-1] < units, "Duplicate/unsorted canonical String")
        canonical.append(units)
    expected = {}
    for alias in aliases:
        key = alias["class_id"], alias["constant"]
        check(key not in expected and 1 <= key[1] <= 65535 and 0 <= alias["canonical"] < len(canonical),
              "Duplicate/invalid source literal binding")
        check(alias["symbol"] == f"boom_batch_literal_load_{key[0]}_{key[1]}", "Invalid literal resolver identity")
        expected[key] = alias["canonical"]
    check(len(canonical) == summary["canonical_strings"] and len(expected) == summary["source_bindings"]
          and summary["root_cells"] == len(canonical)*2, "Literal coverage/root counts differ")
    seen, string_class, field_base = set(), None, 0
    with (ir/"shards.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            shard = json.loads(line)
            path = ir/"shards"/Path(shard["zip"]["path"]).name
            check(file_digest(path) == shard["zip"]["digest"], "Literal IR shard changed")
            with zipfile.ZipFile(path) as bundle:
                for entry in shard["entries"]:
                    raw = bundle.read(entry["path"])
                    # Individual JSON payloads are covered by the verified shard digest.
                    unit = json.loads(raw)
                    check(unit["origin"]["sha256"] == entry["class_sha256"], "Literal class source changed")
                    if dispatch_inputs is not None:
                        for cp in list(dispatch_inputs.get(unit['class_id'], {})):
                            check(cp in unit['constants'], 'Dispatch source constant is missing')
                            dispatch_inputs[unit['class_id']][cp] = unit['constants'][cp]
                            dynamic=unit['constants'][cp].get('InvokeDynamic')
                            if dynamic and dynamic['bootstrap']['owner']=='java/lang/invoke/StringConcatFactory':
                                for arg in dynamic['arguments']:
                                    dispatch_inputs[unit['class_id']][str(arg)]=unit['constants'][str(arg)]
                    if static_inputs is not None:
                        check(unit['class_id'] not in static_inputs,'Duplicate static source class')
                        constants={str(f['constant_value']):unit['constants'][str(f['constant_value'])]
                                   for f in unit['fields'] if f['access']&8 and f['constant_value'] is not None}
                        static_inputs[unit['class_id']]=dict(class_id=unit['class_id'],name=unit['name'],access=unit['access'],
                            source_sha256=unit['origin']['sha256'],major=unit['origin']['java_class_major'],fields=unit['fields'],constants=constants,
                            initializers=[dict(id=m['id'],descriptor=m['descriptor'],access=m['access'],code_sha256=m['code_sha256'])
                                          for m in unit['methods'] if m['name']=='<clinit>'],
                            concrete_instance_method=any(m['access']&(8|0x400)==0 and not m['name'].startswith('<') for m in unit['methods']))
                    if unit["name"] == "java/lang/String" and unit["origin"]["loader"] == "bootstrap":
                        check(string_class is None, "Duplicate bootstrap String")
                        string_class = unit
                    if unit['class_id'] < summary['source_layout']['class_id']:
                        field_base += len(unit['fields'])
                    for cp, value in unit["constants"].items():
                        if "StringUtf16" not in value: continue
                        key = unit["class_id"], int(cp)
                        check(key in expected and canonical[expected[key]] == tuple(value["StringUtf16"]),
                              "Literal binding differs from source IR")
                        check(key not in seen, "Duplicate source literal")
                        seen.add(key)
    check(seen == set(expected), "Literal source bindings missing or invented")
    shape = summary["source_layout"]
    check(string_class is not None and string_class["origin"]["source_id"] == "jdk:java.base"
          and string_class["access"] & 0x10, "Missing original final String")
    check(shape["class_id"] == string_class["class_id"]
          and shape["source_sha256"] == string_class["origin"]["sha256"], "String layout source identity differs")
    layout = None
    with artifact(root, batch["layouts"]).open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["class_id"] == shape["class_id"]: layout = row["candidate"]; break
    check(layout is not None and layout["payload_bytes"] == shape["payload_bytes"]
          and layout["reference_prefix"] == shape["reference_prefix"] == 1 and len(layout["fields"]) == shape["fields"] == 4,
          "Literal layout differs from Java fields")
    for name, desc, key in (("value", "[B", "value_offset"), ("coder", "B", "coder_offset"),
                             ("hash", "I", "hash_offset"), ("hashIsZero", "Z", "hash_is_zero_offset")):
        fields = [f for f in layout["fields"] if f["member"]["name"] == name and f["member"]["descriptor"] == desc]
        check(len(fields) == 1 and fields[0]["offset"] == shape[key], "Literal field offset differs")
    definitions, imports = set(), set()
    texts, entries, thunks = {}, {}, {}
    headers = []
    for index, unit in enumerate(summary["units"]):
        check(unit["id"] == index and unit["object"] and not unit["assembler_diagnostic"], "Missing literal COFF object")
        assembly = artifact(root, unit["assembly"], "string-literals").read_text(encoding="utf-8")
        defined, undefined = coff_symbols(artifact(root, unit["object"], "string-literals"),
                                          frozenset(("WaitOnAddress", "WakeByAddressAll")))
        check(not definitions & defined, "Duplicate literal COFF definition")
        definitions.update(defined); imports.update(undefined)
        for match in re.finditer(r"boom_java_string_literal_text_(\d+) LABEL WORD\n((?: WORD [^\n]+\n)+)", assembly):
            id_ = int(match[1]); check(id_ not in texts, "Duplicate literal text")
            texts[id_] = tuple(int(token.strip(), 16) for line in match[2].splitlines()
                               for token in line[6:].replace("h", "").split(","))
        for match in re.finditer(r"boom_java_string_literal_page_(\d+) LABEL BYTE\n((?: QWORD OFFSET boom_java_string_literal_text_\d+\n DWORD \d+,0[0-9A-F]+h\n)+)", assembly):
            page = int(match[1]); check(page not in entries, "Duplicate literal page")
            entries[page] = [(int(i), int(n), int(h,16)) for i,n,h in re.findall(
                r"text_(\d+)\n DWORD (\d+),0([0-9A-F]+)h", match[2])]
        for match in re.finditer(r"(boom_batch_literal_load_(\d+)_(\d+)) PROC\n lea rdx,boom_java_string_literal_pool\n mov r8d,(\d+)\n jmp boom_java_string_literal\n\1 ENDP", assembly):
            key = int(match[2]), int(match[3]); check(key not in thunks, "Duplicate literal resolver")
            thunks[key] = int(match[4])
        if "boom_java_string_literal_pool DWORD" in assembly: headers.append(assembly)
    check(thunks == expected, "Literal resolver machine-code sources differ")
    check(set(texts) == set(range(len(canonical))) and len(headers) == 1, "Literal text/pool coverage differs")
    for id_, units in enumerate(canonical): check(texts[id_] == (units or (0,)), "Encoded literal data differs")
    expected_entries = [(i,len(units),java_hash(units)) for i,units in enumerate(canonical)]
    check(sorted(entries) == list(range((len(canonical)+255)//256))
          and [entry for page in sorted(entries) for entry in entries[page]] == expected_entries,
          "Paged literal metadata differs")
    header = headers[0]
    normalized = '\n'.join(line.strip() for line in header.splitlines())
    check(f"boom_java_string_literal_pool DWORD 04A534C50h,1,{len(canonical)},1\n" in normalized
          and f"DWORD {shape['value_offset']},{shape['coder_offset']},{shape['hash_offset']},{shape['hash_is_zero_offset']}\nQWORD 0\nDWORD 1,0\n" in normalized
          and f"boom_java_string_literal_roots QWORD {len(canonical)*2} DUP(?)" in header,
          "Literal runtime pool/root layout differs")
    required = {a["symbol"] for a in aliases}
    required.update(f"boom_java_string_literal_text_{i}" for i in range(len(canonical)))
    required.update(f"boom_java_string_literal_page_{i}" for i in entries)
    required.update((f"boom_layout{shape['class_id']}", "boom_heap_ptr", "boom_java_string_literal_pool",
                     "boom_java_string_literal_roots", "boom_java_string_literal_root_count",
                     "boom_java_string_literals_bind_heap", "boom_java_string_literal"))
    check(len(shape['field_maps']) == 4, "Missing String field maps")
    for field in shape['field_maps']:
        slots = [f for f in layout['fields'] if f['member']['index'] == field['declaring_field']]
        check(len(slots) == 1 and slots[0]['offset'] == field['offset']
              and field['symbol'] == f"boom_field_map{field_base+field['declaring_field']}", "Field map differs from source String")
        symbol = field['symbol']
        expected_body = (f"{symbol} PROC FRAME\nsub rsp,40\n.allocstack 40\n.endprolog\nmov r8,rdx\n"
                         f"lea rdx,boom_layout{shape['class_id']}\ncall boom_object_check\ntest rax,rax\n"
                         f"jz {symbol}_done\nadd rax,{field['offset']}\n{symbol}_done:\nadd rsp,40\nret\n{symbol} ENDP")
        check(expected_body in normalized, "String field address resolver differs from source layout")
        required.add(field['symbol'])
    check(definitions == required, "Literal COFF exports differ from source-backed functions/data")
    return dict(verified=True,canonical_strings=len(canonical),source_bindings=len(expected),
                assembly_units=len(summary["units"]),source_layout=shape,linked=False,game_started=False), definitions, imports
