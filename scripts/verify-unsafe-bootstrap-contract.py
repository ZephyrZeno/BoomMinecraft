"""Independent raw class checks for original Unsafe and its Java bootstrap."""
import hashlib
import json
import runpy
import sys
from pathlib import Path

parser = runpy.run_path(str(Path(__file__).with_name("verify-jdk-bridges.py")))
p = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
plan = p["unsafe_bootstrap"]
assert p["schema"] in (52, 53, 72, 73, 76) and not p["full_game_ready"] and not plan["full_unsafe_coverage"]
members = [
    ("Register", "registerNatives", "()V", 0x10A),
    ("ArrayBase", "arrayBaseOffset0", "(Ljava/lang/Class;)I", 0x102),
    ("ArrayScale", "arrayIndexScale0", "(Ljava/lang/Class;)I", 0x102),
    ("ReadLong", "getLongVolatile", "(Ljava/lang/Object;J)J", 0x101),
    ("CasLong", "compareAndSetLong", "(Ljava/lang/Object;JJJ)Z", 0x111),
    ("ReadInt", "getIntVolatile", "(Ljava/lang/Object;J)I", 0x101),
    ("CasInt", "compareAndSetInt", "(Ljava/lang/Object;JII)Z", 0x111),
    ("StaticOffset", "staticFieldOffset0", "(Ljava/lang/reflect/Field;)J", 0x102),
    ("StaticBase", "staticFieldBase0", "(Ljava/lang/reflect/Field;)Ljava/lang/Object;", 0x102),
    ("FullFence", "fullFence", "()V", 0x101),
    ("ObjectOffset", "objectFieldOffset1", "(Ljava/lang/Class;Ljava/lang/String;)J", 0x102),
    ("ReadBoolean", "getBooleanVolatile", "(Ljava/lang/Object;J)Z", 0x101),
    ("ExchangeByte", "compareAndExchangeByte", "(Ljava/lang/Object;JBB)B", 0x11),
]
for owner, origin, digest, length in [
    ("jdk/internal/misc/Unsafe", plan["origin"], plan["initializer_code_sha256"], 236),
    ("jdk/internal/misc/UnsafeConstants", plan["constants_origin"], plan["constants_initializer_code_sha256"], 21),
]:
    source = next(s for s in p["sources"] if s["class_name"] == owner)
    data = Path(source["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == source["origin"]["sha256"] == origin["sha256"]
    assert origin["loader"] == "bootstrap" and origin["source_id"] == "jdk:java.base" and not origin.get("generated")
    c = parser["parse"](data)
    init = next(m for m in c["methods"] if m[1:3] == ("<clinit>", "()V"))
    body = next(b for n, b in init[3] if n == "Code")
    n = int.from_bytes(body[4:8], "big")
    assert n == length and hashlib.sha256(body[8:8+n]).hexdigest() == digest
    assert any(s["class_name"] == owner and s["method"] == "<clinit>" for s in p["symbols"])
    if owner.endswith("/Unsafe"):
        assert sum(bool(m[0] & 0x100) for m in c["methods"]) == plan["native_declarations"]
        for _, name, desc, flags in members:
            m = next(m for m in c["methods"] if m[1:3] == (name, desc))
            assert m[0] == flags
            code = next((b for n,b in m[3] if n == "Code"), None)
            if flags & 0x100: assert code is None
            else:
                assert name == 'compareAndExchangeByte' and code is not None
                n=int.from_bytes(code[4:8],'big')
                assert hashlib.sha256(code[8:8+n]).hexdigest()==plan['java_intrinsic_code_sha256']


def constants(data):
    parsed = parser["parse"](data)
    r = parser["Reader"](parsed["cp"])
    cp, i = {}, 1
    while i < parsed["count"]:
        tag = r.u1()
        if tag == 1: cp[i] = (tag, r.take(r.u2()).decode("utf-8", errors="replace"))
        elif tag in (7, 8, 16, 19, 20): cp[i] = (tag, r.u2())
        elif tag in (9, 10, 11, 12, 17, 18): cp[i] = (tag, r.u2(), r.u2())
        elif tag in (3, 4): r.take(4)
        elif tag in (5, 6): r.take(8); i += 1
        elif tag == 15: r.take(3)
        else: raise AssertionError("Unknown constant tag")
        i += 1
    return cp


for b in plan["bindings"]:
    source = next(s for s in p["sources"] if s["origin"] == b["caller"])
    data = Path(source["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == b["caller"]["sha256"]
    cp = constants(data)
    ref = cp[b["constant"]]
    assert ref[0] == 10 and cp[ref[1]][0] == 7
    assert cp[cp[ref[1]][1]] == (1, "jdk/internal/misc/Unsafe")
    nt = cp[ref[2]]
    _, name, desc, _ = next(m for m in members if m[0] == b["operation"])
    assert nt[0] == 12 and cp[nt[1]] == (1, name) and cp[nt[2]] == (1, desc)
    if b["operation"] in ("Register", "ArrayBase", "ArrayScale", "StaticOffset", "StaticBase", "ObjectOffset"):
        assert b["caller"] == plan["origin"]
assert plan['full_fence_supported'] and plan['abi']==3 and plan['executable_native_declarations']==sum(bool(m[3]&0x100) for m in members) and plan['executable_operations']==len(members) and plan['int_array_operations'] and not plan['long_array_and_thread_counter_only']
print(json.dumps(dict(passed=True, original_initializers=2, original_native_declarations=plan["native_declarations"], executable_native_declarations=plan["executable_native_declarations"], executable_operations=len(members), Java_intrinsic_declarations=1, callsite_constants_verified=len(plan["bindings"]), full_unsafe_coverage=False)))
