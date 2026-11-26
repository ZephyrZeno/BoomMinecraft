# Original System phase 3 owner

The new `scripts/vm-system-phase3.py` and
`native/entry/system_phase3.asm.inc` provide a source-bound owner for the intact
original `java/lang/System.initPhase3()V`. Shared native entry integration and
actual Phase3 execution now pass on the verified 29-provider source selection.
Minecraft entry execution and world startup remain incomplete.

The original locked method is private static, ID 43962, class 4699, 427 Code
bytes, SHA256 `52a98868c6762cbd222e079c0d82e741110d3fc944dfdb5cc9231963466f9efc`.
Its first explicit initialization is
`Unsafe.ensureClassInitialized(StringConcatFactory.class)`. Security-manager
property handling, reflection, typed exceptions and warning output remain in
the complete original Java method. No property or branch is replaced.

The final source sequence is `VM.initLevel(3)` at PC408,
`ClassLoader.initSystemClassLoader()` at PC411, `Thread.currentThread()` at
PC415, `Thread.setContextClassLoader` at PC419, `VM.initLevel(4)` at PC423,
and the sole normal return at PC426. These are source Java actions. The ASM
owner never assigns VM levels, loader fields, Java state, or class initialization
state. It calls original method 43962 exactly once, only with an initially clean
Context and VM level 2; success requires a clean returned Context and VM level 4.

`contract(summary, owner, S, reader)` independently checks the original Class
inventory and Code using both existing source readers, derives dependencies
and level arguments, and records complete calls, literals and exception
handlers. `bind(closure, summary, owner, S, reader)` additionally requires the
intact method in the independently verified selected closure. The accepted 29
source closure already contains this original method. Its binding was tested
without selecting or rewriting new Java code in
`.boom/system-phase3-development/original-phase3-model.json` (SHA256
`8cba08ea1337f00c48285b2d5c9020da1f8727601468fb4bf2434fe5e9560d6d`).

The owner exposes private procedure `boom_vm_call_system_phase3` with Context32
in RCX and report pointer in RDX. The emitter supplies
`ORIGINAL_SYSTEM_PHASE3` and `VM_LEVEL_CELL`. It returns boolean EAX, without
altering the game's Context. Report544/ABI13 preserves the original first448
bytes and owner-reserved bytes448..511, appending:

| Offset | Observation |
| --- | --- |
| 512 | Original phase3 called |
| 516 | Original phase3 returned with normal Context |
| 520 | VM level before |
| 524 | VM level after |
| 528 | Latest main Context kind |
| 532 | Latest main Context PC |
| 536 | Latest main Context method |
| 540 | Latest main Context depth |

`tests/vm_system_phase3.py` checks actual source binding and rejection of
unselected, changed, generated or wrong-loader inputs. Its real-ml64 COFF test
checks the original Java call, VM-cell read relocations, and that all explicit
report stores stay in the new report tail. It does not replace original Java
with a test stub or count the owner-only COFF as game execution.

The shared build/prepare/invoke tools accept `--system-phase3` / `-SystemPhase3`
and retain original Phase1 and Phase2 as prerequisites. The process owner calls
the intact original method after successful Phase2. No independent source/Java
compilation is repeated when an accepted selection already contains Phase3.
`decode-vm-entry-report.py` decodes exact old and new report layouts, is sealed
with `Run-VmEntry.ps1` in the native manifest, and checks each stage separately.
The old main Context prefix records the latest main-thread state; a later
Phase3 source failure does not turn an earlier Phase2 return into a failure.

Actual sealed execution in `.boom/vm-entry-images/v149-phase3-sealed-b` completed
original Phase1/2/3 with VM levels 1→2→4, exit0, Context0/depth0, no source fault,
and cleanup7. Two original worker exits and two OS record reaps completed with
zero worker/signal failures, held monitors, and registry locks. Live objects
before teardown were 13360. There is no automatic collection claim.

```text
native manifest a76bf4fdd3e79c3bf0e1b4d5cb3fabf802bced34a5d26d9d687c034ae1492051
native proof    a56aa701a0075a02505392505f705d46d622eae1527bbd44fc8592b2d020d7de
execution       007971a9a797da52215771f37e16d1c2112b15a27a0edb8827fd639554dd9da2
ABI13 report    9ffeff7e07a67e5f4c44ccf04e31bb21abb85f7713c1f04d688edeade4441008
```

The separately scoped `.boom/accepted-system-phase3-v150.json`, SHA256
`4850a6478d3a9f9be8868984478b724144811eb981ba0956c12d30f5220d3897`, rehashes
286 artifacts twice and archives 15 build/verification/entry source inputs.
The earlier `v149-phase3-first-a` raw execution remains separate: it genuinely
returned VM4, but its manifest predates the new decoder pin. It is not substituted
for the fresh sealed-b execution. Original accepted29/31 input states are not
rewritten by this System milestone. Full VM/game/world flags remain false.
