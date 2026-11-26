"""Verify the class-initialization dependency refresh against the actual old/new DLLs."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def prove(root, art, base, old_sources, old_runtime, combined, regression, artifact, script):
    helpers = script("unsafe-thread-counter-compatibility")
    check = helpers.check
    sources = ("classes32.asm", "unwind.asm")
    check(all(p.is_relative_to(art) for p in (old_sources, old_runtime, combined, regression)),
          "Class initializer evidence must remain in project artifacts")
    old_dll, new_dll = old_runtime / "boom-runtime.dll", combined / "boom-runtime.dll"
    metadata = [json.loads((p / "runtime.json").read_text(encoding="utf-8-sig")) for p in (old_runtime, combined)]
    for directory, dll, m in zip((old_runtime,combined), (old_dll,new_dll), metadata):
        check(Path(m["dll"]).resolve() == dll and artifact(dll)["digest"]["sha256"] == m["sha256"] and
              m["implementation_language"] == "x86-64 MASM assembly" and
              not any(m[k] for k in ("java_runtime","rust_runtime","c_runtime")), "Incorrect assembly runtime identity")
    check(metadata[0]["sources"][helpers.FIELD] == metadata[1]["sources"][helpers.FIELD] and
          metadata[0]["sources"][helpers.REGISTRY] == metadata[1]["sources"][helpers.REGISTRY],
          "Comparison runtime must have the same UFL2 field and counter kernels")
    exports = script("diagnostic-closure").pe_exports
    original_exports, combined_exports = exports(old_dll), exports(new_dll)
    evidence = {}
    for filename, changed in zip(sources, ("boom_class_ensure32","boom_exception_init_failure")):
        name = "native/runtime/" + filename
        files = [old_sources / filename, root / name]
        rec = [artifact(f) for f in files]
        check(all(m["sources"][name] == item["digest"]["sha256"] for m,item in zip(metadata,rec)),
              "Unmatched snapshot/working initializer source")
        if filename == "classes32.asm":
            check(all(base[family]["kernel_sha256"][name] == rec[0]["digest"]["sha256"] for family in ("frames","class_lookup")),
                  "Inherited class initializer dependencies differ from old snapshot")
        old, new = [f.read_text(encoding="utf-8-sig") for f in files]
        a,b = helpers.procedures(old), helpers.procedures(new)
        check(a.keys() == b.keys() and {n for n in a if a[n] != b[n]} == {changed},
              "Unexpected class/exception procedure changes")
        check(helpers.instructions(old.replace(a[changed],"",1)) == helpers.instructions(new.replace(b[changed],"",1)),
              "Class initializer external ABI/data/imports/other code changed")
        public = set(re.findall(r"(?m)^PUBLIC (\w+)\s*$",old))
        check(public <= original_exports and public <= combined_exports, "Missing actual assembly DLL exports")
        lines = helpers.instructions(a[changed])
        if filename == "classes32.asm":
            at = lines.index("class32_publish_failure:")
            cause = ["mov rax,QWORD PTR [rsi+16]", "mov r10,QWORD PTR [rbx+56]", "mov QWORD PTR [r10],rax"]
            j = lines.index(cause[0], at)
            check(lines[j:j+3] == cause, "Original pending cause publication differs")
            del lines[j:j+3]
            j = lines.index("call boom_exception_init_failure", at)+1
            lines[j:j] = cause[1:]
        else:
            def insert_after(anchor, text):
                check(lines.count(anchor)==1,"Unrecognized exception contract anchor")
                i = lines.index(anchor)+1
                lines[i:i] = text.splitlines()
            insert_after("mov rbx,rcx", "test rbx,rbx\njz exception_init_failure_no_context")
            insert_after("mov rsi,QWORD PTR [rbx+24]", """test rsi,rsi
jz exception_init_failure_unbound
cmp DWORD PTR [rsi],04558564Dh
jne exception_init_failure_invalid
cmp DWORD PTR [rsi+4],1
jne exception_init_failure_invalid
cmp DWORD PTR [rsi+8],2
jne exception_init_failure_unbound
cmp QWORD PTR [rsi+32],0
je exception_init_failure_invalid
cmp QWORD PTR [rsi+48],0
je exception_init_failure_invalid""")
            insert_after("exception_init_failure_done:", """mov rax,QWORD PTR [rbx+16]
jmp exception_init_failure_return
exception_init_failure_unbound:
mov edx,20
jmp exception_init_failure_raw
exception_init_failure_invalid:
mov edx,7
exception_init_failure_raw:
mov rax,QWORD PTR [rbx+16]
mov QWORD PTR [rbx+16],0
mov DWORD PTR [rbx],edx
jmp exception_init_failure_return
exception_init_failure_no_context:
xor eax,eax
exception_init_failure_return:""")
        check(lines == helpers.instructions(b[changed]), "Class initializer behavior differs from specified delta")
        evidence[name] = dict(previous=rec[0], current=rec[1], modified_proc=changed, public=sorted(public),
                              imports=sorted(re.findall(r"(?m)^EXTERN (\w+):PROC\s*$", new)))
    test = root / "tests/monitor_wait/test_unbound_init.py"
    report = json.loads(regression.read_text(encoding="utf-8-sig"))
    expected = [dict(plan=plan,source_failure_kind=kind,source_pc=42,original_cause_retained=True)
                for plan,kind in (("absent",20),("foreign ABI",7),("not ready",20),("invalid type map",7))]
    check(report == dict(passed=True,runtime_sha256=metadata[1]["sha256"],cases=expected),
          "Regression cases are incomplete or belong to another runtime")
    with tempfile.TemporaryDirectory(prefix="class-init-replay-",dir=art) as tmp:
        fresh = Path(tmp)/"regression.json"
        subprocess.run([sys.executable,str(test),"--runtime",str(combined),"--output",str(fresh)],
                       cwd=root, check=True, timeout=40, stdout=subprocess.PIPE)
        check(json.loads(fresh.read_text(encoding="utf-8-sig")) == report, "Real DLL regression replay differs")
    return dict(previous_manifest=artifact(old_runtime/"runtime.json"), previous_dll=artifact(old_dll),
                combined_manifest=artifact(combined/"runtime.json"), combined_dll=artifact(new_dll),
                sources=evidence, context_bytes=32, class_descriptor_bytes=64, class_descriptor_abi=2,
                cause_root_offset=56, failure_state=3, ready_exception_path_instructions_preserved=True,
                regression=artifact(regression), test=artifact(test), test_host=artifact(test.with_name("test_wait.py")),
                real_dll_replay_cases=expected)
