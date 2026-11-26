"""Verify symbolic IR against original class bytes, without executing guest code."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return dict(size=len(data), sha1=hashlib.sha1(data).hexdigest(), sha256=hashlib.sha256(data).hexdigest())


class Reader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, size):
        end = self.position + size
        check(end <= len(self.data), "Truncated source class")
        data = self.data[self.position:end]
        self.position = end
        return data

    def u1(self): return self.take(1)[0]
    def u2(self): return int.from_bytes(self.take(2), "big")
    def u4(self): return int.from_bytes(self.take(4), "big")


class Source:
    def __init__(self, data):
        r = Reader(data)
        check(r.u4() == 0xcafebabe, "Bad source class magic")
        r.take(4)
        self.cp = [None] * r.u2()
        index = 1
        while index < len(self.cp):
            tag = r.u1()
            if tag == 1: value = r.take(r.u2())
            elif tag in (3, 4): value = r.take(4)
            elif tag in (5, 6): value = r.take(8)
            elif tag in (7, 8, 16, 19, 20): value = r.u2()
            elif tag in (9, 10, 11, 12, 17, 18): value = (r.u2(), r.u2())
            elif tag == 15: value = (r.u1(), r.u2())
            else: raise ValueError(f"Unknown source constant {tag}")
            self.cp[index] = tag, value
            index += 2 if tag in (5, 6) else 1
        self.access, this, parent = r.u2(), r.u2(), r.u2()
        self.name = self.class_name(this)
        self.parent = self.class_name(parent) if parent else ""
        self.interfaces = [self.class_name(r.u2()) for _ in range(r.u2())]
        self.fields = []
        for _ in range(r.u2()):
            access, name, descriptor = r.u2(), self.text(r.u2()), self.text(r.u2())
            attrs = self.attributes(r)
            values = [int.from_bytes(b, "big") for n, b in attrs if n == "ConstantValue"]
            self.fields.append(dict(name=name, descriptor=descriptor, access=access,
                                    constant_value=values[0] if values else None))
        self.methods = []
        for _ in range(r.u2()):
            access, name, descriptor = r.u2(), self.text(r.u2()), self.text(r.u2())
            self.methods.append(dict(access=access, name=name, descriptor=descriptor, attrs=self.attributes(r)))
        self.attrs = self.attributes(r)
        check(r.position == len(data), "Trailing source class data")
        self.bootstraps = []
        for name, body in self.attrs:
            if name == "BootstrapMethods":
                b = Reader(body)
                for _ in range(b.u2()):
                    handle = b.u2()
                    self.bootstraps.append((handle, [b.u2() for _ in range(b.u2())]))

    def units(self, index):
        tag, raw = self.cp[index]
        check(tag == 1, "Expected source UTF8")
        value = raw.replace(b"\xc0\x80", b"\x00").decode("utf-8", errors="surrogatepass")
        data = value.encode("utf-16-le", errors="surrogatepass")
        return list(struct.unpack("<" + "H" * (len(data) // 2), data))

    def text(self, index):
        units = self.units(index)
        return struct.pack("<" + "H" * len(units), *units).decode("utf-16-le", errors="surrogatepass")

    def class_name(self, index):
        tag, name = self.cp[index]
        check(tag == 7, "Expected source Class")
        return self.text(name)

    def attributes(self, reader):
        result = []
        for _ in range(reader.u2()):
            name = self.text(reader.u2())
            result.append((name, reader.take(reader.u4())))
        return result

    def member(self, index):
        tag, (owner, signature) = self.cp[index]
        check(tag in (9, 10, 11), "Expected source member")
        _, (name, descriptor) = self.cp[signature]
        result = dict(owner=self.class_name(owner), name=self.text(name), descriptor=self.text(descriptor))
        if tag != 9: result["interface"] = tag == 11
        return result

    def symbol(self, index):
        tag, value = self.cp[index]
        if tag in (3, 4, 5, 6):
            return {{3: "Int", 4: "FloatBits", 5: "Long", 6: "DoubleBits"}[tag]:
                    int.from_bytes(value, "big", signed=tag in (3, 5))}
        if tag == 7: return {"Class": self.class_name(index)}
        if tag == 8: return {"StringUtf16": self.units(value)}
        if tag in (9, 10, 11): return {"Field" if tag == 9 else "Method": self.member(index)}
        if tag == 15:
            kind, target = value
            handle = self.member(target)
            handle.setdefault("interface", False)
            handle["reference_kind"] = kind
            return {"Handle": handle}
        if tag == 16: return {"MethodType": self.text(value)}
        if tag in (17, 18):
            bootstrap, signature = value
            _, (name, descriptor) = self.cp[signature]
            handle, arguments = self.bootstraps[bootstrap]
            site = dict(name=self.text(name), descriptor=self.text(descriptor),
                        bootstrap=self.symbol(handle)["Handle"], arguments=arguments)
            return {"Dynamic" if tag == 17 else "InvokeDynamic": site}
        raise ValueError(f"Unexpected IR constant tag {tag}")

    def code(self, method):
        codes = [data for name, data in method["attrs"] if name == "Code"]
        if not codes: return None
        r = Reader(codes[0])
        max_stack, max_locals = r.u2(), r.u2()
        code = r.take(r.u4())
        handlers = []
        for _ in range(r.u2()):
            start, end, target, catch = r.u2(), r.u2(), r.u2(), r.u2()
            handlers.append(dict(start=start, end=end, target=target,
                                 catch_type=self.class_name(catch) if catch else None))
        lines = []
        for name, data in self.attributes(r):
            if name == "LineNumberTable":
                table = Reader(data)
                lines.extend(dict(pc=table.u2(), line=table.u2()) for _ in range(table.u2()))
        check(r.position == len(codes[0]), "Source Code attribute length differs")
        return dict(bytes=code, max_stack=max_stack, max_locals=max_locals, handlers=handlers, lines=lines)


def descriptor(text):
    position = 1
    def ty():
        nonlocal position
        char = text[position]
        position += 1
        if char == "L":
            end = text.index(";", position)
            name = text[position:end]
            position = end + 1
            return {"Object": name}
        if char == "[":
            dimensions = 1
            while text[position] == "[":
                dimensions += 1
                position += 1
            return {"Array": dict(dimensions=dimensions, element=ty())}
        return dict(Z="Boolean", B="Byte", C="Char", S="Short", I="Int", J="Long",
                    F="Float", D="Double", V="Void")[char]
    check(text.startswith("("), "Bad source method descriptor")
    parameters = []
    while text[position] != ")": parameters.append(ty())
    position += 1
    result = ty()
    check(position == len(text), "Trailing source descriptor")
    return dict(parameters=parameters, result=result)


def stream(code):
    """Read operand values directly from source bytes; no IR boundaries trusted."""
    pc = 0
    u2 = lambda at: int.from_bytes(code[at:at+2], "big")
    s2 = lambda at: int.from_bytes(code[at:at+2], "big", signed=True)
    s4 = lambda at: int.from_bytes(code[at:at+4], "big", signed=True)
    while pc < len(code):
        op, operand, wide, size = code[pc], "None", None, 1
        if op == 0x10:
            operand, size = {"Immediate": int.from_bytes(code[pc+1:pc+2], "big", signed=True)}, 2
        elif op == 0x11: operand, size = {"Immediate": s2(pc+1)}, 3
        elif op == 0x12: operand, size = {"Constant": code[pc+1]}, 2
        elif op in (0x13, 0x14, 0xbb, 0xbd, 0xc0, 0xc1) or 0xb2 <= op <= 0xb8:
            operand, size = {"Constant": u2(pc+1)}, 3
        elif 0x15 <= op <= 0x19 or 0x36 <= op <= 0x3a or op == 0xa9:
            operand, size = {"Local": code[pc+1]}, 2
        elif 0x1a <= op <= 0x2d: operand = {"Local": (op-0x1a) % 4}
        elif 0x3b <= op <= 0x4e: operand = {"Local": (op-0x3b) % 4}
        elif op == 0x84:
            operand = {"Increment": dict(local=code[pc+1], amount=int.from_bytes(code[pc+2:pc+3], "big", signed=True))}
            size = 3
        elif 0x99 <= op <= 0xa8 or op in (0xc6, 0xc7): operand, size = {"Branch": pc+s2(pc+1)}, 3
        elif op in (0xc8, 0xc9): operand, size = {"Branch": pc+s4(pc+1)}, 5
        elif op in (0xaa, 0xab):
            base = (pc+4) & ~3
            cases = []
            if op == 0xaa:
                low, high = s4(base+4), s4(base+8)
                for i, key in enumerate(range(low, high+1)): cases.append([key, pc+s4(base+12+i*4)])
                end = base+12+len(cases)*4
            else:
                for i in range(s4(base+4)): cases.append([s4(base+8+i*8), pc+s4(base+12+i*8)])
                end = base+8+len(cases)*8
            operand, size = {"Switch": dict(default=pc+s4(base), cases=cases)}, end-pc
        elif op == 0xb9: operand, size = {"Interface": dict(constant=u2(pc+1), count=code[pc+3])}, 5
        elif op == 0xba: operand, size = {"Constant": u2(pc+1)}, 5
        elif op == 0xbc: operand, size = {"PrimitiveArray": code[pc+1]}, 2
        elif op == 0xc4:
            wide, size = code[pc+1], 6 if code[pc+1] == 0x84 else 4
            operand = {"Increment": dict(local=u2(pc+2), amount=s2(pc+4))} if wide == 0x84 else {"Local": u2(pc+2)}
        elif op == 0xc5: operand, size = {"MultiArray": dict(constant=u2(pc+1), dimensions=code[pc+3])}, 4
        check(pc+size <= len(code), "Truncated source instruction")
        yield dict(pc=pc, opcode=op, wide_opcode=wide, next=pc+size, operand=operand)
        pc += size


def successors(instruction, length):
    op = instruction["wide_opcode"] or instruction["opcode"]
    operand = instruction["operand"]
    if isinstance(operand, dict) and "Switch" in operand:
        switch = operand["Switch"]
        return sorted({switch["default"], *(row[1] for row in switch["cases"])})
    if isinstance(operand, dict) and "Branch" in operand:
        result = {operand["Branch"]}
        if op not in (0xa7, 0xc8) and instruction["next"] < length: result.add(instruction["next"])
        return sorted(result)
    if 0xac <= op <= 0xb1 or op in (0xbf, 0xa9): return []
    return [instruction["next"]] if instruction["next"] < length else []


def verify_body(body, source):
    code = source["bytes"]
    instructions = body["instructions"]
    check(body["max_stack"] == source["max_stack"] and body["max_locals"] == source["max_locals"]
          and body["code_length"] == len(code), "IR Code bounds differ from source")
    count = 0
    for count, original in enumerate(stream(code), 1):
        check(count <= len(instructions) and instructions[count-1] == original,
              f"IR instruction/operand differs from source at {original['pc']}")
    check(count == len(instructions), "IR instruction inventory differs")
    check(body["handlers"] == source["handlers"], "IR exception row order/values differ")
    positions = {i["pc"]: n for n, i in enumerate(instructions)}
    leaders = {0}
    legacy = False
    for inst in instructions:
        op = inst["wide_opcode"] or inst["opcode"]
        legacy |= op in (0xa8, 0xa9, 0xc9)
        operand = inst["operand"]
        branch = isinstance(operand, dict) and bool({"Branch", "Switch"} & operand.keys())
        if branch:
            targets = successors(inst, len(code))
            check(all(n in positions for n in targets), "IR target is not an instruction boundary")
            leaders.update(targets)
        if (branch or 0xac <= op <= 0xb1 or op in (0xbf, 0xa9)) and inst["next"] < len(code):
            leaders.add(inst["next"])
    for row in source["handlers"]:
        leaders.update((row["start"], row["target"]))
        if row["end"] < len(code): leaders.add(row["end"])
    leaders = sorted(leaders)
    check(len(leaders) == len(body["blocks"]), "IR basic block coverage differs")
    for n, start in enumerate(leaders):
        end = leaders[n+1] if n+1 < len(leaders) else len(code)
        first, limit = positions[start], positions.get(end, len(instructions))
        expected = dict(start=start, end=end, first_instruction=first, instruction_count=limit-first,
                        successors=successors(instructions[limit-1], len(code)),
                        handlers=[j for j, h in enumerate(source["handlers"]) if h["start"] <= start < h["end"]])
        check(body["blocks"][n] == expected, "IR block edges/protected region differ")
    check(body["contains_legacy_subroutines"] == legacy, "IR legacy subroutine flag differs")


def counts(unit):
    result = Counter(methods=len(unit["methods"]), constants=len(unit["constants"]))
    for method in unit["methods"]:
        result["java_methods"] += method["code_sha256"] is not None
        result["native_declarations"] += bool(method["access"] & 0x100)
        result["abstract_declarations"] += bool(method["access"] & 0x400)
        result["failed_methods"] += method["diagnostic"] is not None
        body = method["body"]
        result["symbolic_java_methods"] += body is not None
        result["legacy_subroutine_methods"] += bool(body and body["contains_legacy_subroutines"])
        result["instructions"] += len(body["instructions"]) if body else 0
        result["blocks"] += len(body["blocks"]) if body else 0
    return result


def verify(root, plan, lock, base, require_all=False):
    root, plan, base = Path(root), Path(plan), Path(base)
    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))
    summary, input_plan, inputs = read(root/"summary.json"), read(plan/"summary.json"), read(lock)
    check(summary["mode"] == "symbolic_ir_only" and summary["schema"] == 1, "Unexpected IR schema/mode")
    check(summary["input_fingerprint"] == input_plan["input_fingerprint"] == inputs["fingerprint"], "IR input identity differs")
    check(summary["jdk_fingerprint"] == input_plan["jdk_fingerprint"] == read(base)["fingerprint"], "IR JDK identity differs")
    check(summary["source_plan_fingerprint"] == input_plan["planner_fingerprint"], "IR plan identity differs")
    for flag in ("type_layout_and_link_verified", "game_started", "world_created", "full_game_ready"):
        check(summary[flag] is False, f"IR incorrectly claims {flag}")
    check(summary["assembly_emitted_methods"] == 0, "IR cannot claim assembly emission")
    class_data = (plan/"classes.jsonl").read_bytes()
    check(digest(class_data) == input_plan["artifacts"]["classes"]["digest"], "Source class plan changed")
    classes = [json.loads(line) for line in class_data.splitlines()]
    index_data = (root/"shards.jsonl").read_bytes()
    check(digest(index_data) == summary["index"]["digest"], "IR index digest differs")
    shards = [json.loads(line) for line in index_data.splitlines()]
    check(len(shards) == summary["shards"], "IR shard coverage differs")
    paths = {item["id"]: Path(item["path"]) for item in inputs["files"]}
    archives, seen, methods_seen = {}, set(), set()
    total, class_failures = Counter(), 0
    try:
        for shard in shards:
            zip_path = root/"shards"/Path(shard["zip"]["path"]).name
            check(digest(zip_path.read_bytes()) == shard["zip"]["digest"], "IR shard digest differs")
            with zipfile.ZipFile(zip_path) as bundle:
                check(set(bundle.namelist()) == {e["path"] for e in shard["entries"]}, "IR shard entry coverage differs")
                for entry in shard["entries"]:
                    class_id = entry["class_id"]
                    check(class_id not in seen and 0 <= class_id < len(classes), "Duplicate/invalid IR class")
                    seen.add(class_id)
                    data = bundle.read(entry["path"])
                    check(digest(data) == entry["digest"], "IR class payload digest differs")
                    unit, expected = json.loads(data), classes[class_id]
                    check(unit["class_id"] == class_id and unit["origin"] == expected["origin"], "IR class source identity differs")
                    check(not unit["assembly_emitted"] and not unit["type_layout_and_link_verified"], "IR class claims executable success")
                    origin = unit["origin"]
                    if origin["source_id"].startswith("jdk:"): raw = (base.parent/"image"/origin["jar_entry"]).read_bytes()
                    else:
                        path = paths[origin["source_id"]]
                        if path not in archives: archives[path] = zipfile.ZipFile(path)
                        raw = archives[path].read(origin["jar_entry"])
                    check(hashlib.sha256(raw).hexdigest() == origin["sha256"] == entry["class_sha256"], "Original class bytes changed")
                    source = Source(raw)
                    check(unit["name"] == source.name == expected["name"]
                          and unit["access"] == source.access and unit["superclass"] == source.parent
                          and unit["interfaces"] == source.interfaces, "IR class declaration differs")
                    check([m["id"] for m in unit["methods"]] == expected["method_ids"], "IR method plan coverage differs")
                    check(len(unit["methods"]) == len(source.methods), "IR source method coverage differs")
                    if unit["diagnostic"] is None:
                        check(unit["fields"] == source.fields, "IR field declarations differ")
                        for index, symbol in unit["constants"].items():
                            check(source.symbol(int(index)) == symbol, "IR symbolic constant differs from source")
                            for kind in ("Dynamic", "InvokeDynamic"):
                                if kind in symbol:
                                    check(all(str(arg) in unit["constants"] for arg in symbol[kind]["arguments"]),
                                          "IR bootstrap argument is missing from constant table")
                        check(all(f["constant_value"] is None or str(f["constant_value"]) in unit["constants"]
                                  for f in unit["fields"]), "IR field constant is missing")
                        for member, original in zip(unit["methods"], source.methods):
                            check(all(member[k] == original[k] for k in ("name", "descriptor", "access")), "IR method declaration differs")
                            raw_code = source.code(original)
                            check(member["code_sha256"] == (hashlib.sha256(raw_code["bytes"]).hexdigest() if raw_code else None), "IR method Code digest differs")
                            if member["diagnostic"] is None:
                                check(member["signature"] == descriptor(original["descriptor"]), "IR method descriptor types differ")
                            if member["body"] is not None:
                                check(member["diagnostic"] is None and raw_code is not None, "IR body has a diagnostic or lacks source Code")
                                verify_body(member["body"], raw_code)
                                for inst in member["body"]["instructions"]:
                                    operand = inst["operand"]
                                    index = None
                                    if isinstance(operand, dict):
                                        if "Constant" in operand: index = operand["Constant"]
                                        elif "Interface" in operand: index = operand["Interface"]["constant"]
                                        elif "MultiArray" in operand: index = operand["MultiArray"]["constant"]
                                    if index is not None:
                                        check(str(index) in unit["constants"], "IR instruction constant is missing")
                                check(member["line_numbers"] == raw_code["lines"], "IR source line table differs")
                            elif raw_code is not None:
                                check(member["diagnostic"] is not None, "Missing Java body was not reported")
                    else: class_failures += 1
                    for member in unit["methods"]:
                        check(member["id"] not in methods_seen, "Duplicate IR method")
                        methods_seen.add(member["id"])
                    actual = counts(unit)
                    check(all(actual[key] == value for key, value in entry["counts"].items()), "IR entry counts differ")
                    total.update(actual)
    finally:
        for archive in archives.values(): archive.close()
    check(len(seen) == summary["classes"] == len(classes), "IR class inventory is truncated")
    check(len(methods_seen) == input_plan["methods"] and methods_seen == set(range(input_plan["methods"])), "IR method inventory is truncated")
    check(class_failures == summary["class_failures"], "IR class diagnostic total differs")
    check(all(total[key] == value for key, value in summary["counts"].items()), "IR summary counts differ")
    if require_all: check(class_failures == total["failed_methods"] == 0, "IR contains frontend failures")
    return dict(verified=True, scope="symbolic_IR_source_operands_constants_CFG_and_coverage_only",
                classes=len(seen), methods=len(methods_seen), counts=dict(total),
                type_layout_and_link_verified=False, assembly_emitted_methods=0,
                game_started=False, world_created=False, full_game_ready=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir", type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--jdk-base", required=True, type=Path)
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.ir, args.plan, args.lock, args.jdk_base, args.require_all)
    if args.output: args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
