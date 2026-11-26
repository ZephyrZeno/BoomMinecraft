# Original dedicated-server Main bridge

`scripts/vm-game-entry.py` binds the locked vanilla-application
`net/minecraft/server/Main` from
`server/versions/1.21.1/server-1.21.1.jar`. It reads the original archive/class,
major65, method inventory, Code and exception handlers. Class and method IDs
come from that source catalog. This batch's evidence is class49839,
main491841 (921 bytes, SHA-256
`ced9dcc32f82b4cf43bcebea2a6c5dcd1a254caa703490ce3ef449dd5a6a18ce`),
and `<clinit>`491849 (7 bytes, SHA-256
`06e366c338567d85831e546a3c07752be861a98a3a69857b0556d7f61b52ee27`).
The original initializer calls `com/mojang/logging/LogUtils.getLogger` and stores
the result into Main's original static Logger field. That Java dependency must
be selected and executed normally; the bridge does not bypass logging.

The original Main is linked into the verified native31 entry. Actual execution
completes all three original System phases and enters Main's original logger
initialization, where the standard entry stops at the missing
`Class.getDeclaredMethods0` implementation. Main's body and help output have not
completed. The current107 source rebuild and its extra original Java
dependencies are recorded in [VM_ADDITIONAL_SOURCE_ROOTS.md](VM_ADDITIONAL_SOURCE_ROOTS.md).
Help completion will itself remain a bounded entry test.

## Owner API

```python
G.contract(summary, owner, S, R, arguments=('--help',))
G.bind(closure, summary, owner, S, R, arguments=('--help',))
G.data(model)
```

`S` is the existing runtime-provider source helper and `R` is the independent
original-Code reader from `verify-batch-frames.py`. `owner` must be the actual
Main record from the validated plan. `contract` is usable before Main is
selected and marks `selected=false`. `bind` additionally requires intact main
and `<clinit>` Code, the normal Main class descriptor, and actual properties COFF
in the closure. It rejects the historical29 source, where Main is not selected.

Top-level model fields `method`, `symbol`, and `class_id` match the phase helpers'
style. `main` and `initializer` contain complete source identities. The precise
initial roots are available as `source_class_roots`, `source_method_roots`,
`source_initializer_method_roots`, and `source_cli_entries`:

```text
vanilla-application:net/minecraft/server/Main
vanilla-application:net/minecraft/server/Main:main:([Ljava/lang/String;)V
```

Admit Main, its original logger initializer and all further Java dependencies
through ordinary source selection. Preserve the source Code and its handlers.
The properties and runtime_metadata modules must actually be selected;
`selected_property_natives` is not a substitute for the properties object.

`G.data` emits compiler-owned UTF16 argument text and a local public
`boom_game_argv_text_rows` table, with 16-byte rows `(pointer, units, reserved)`.
Its origin is explicitly `boom:owned-server-entry-argv-v1`, not JDK or game
classfile input. The initial argument list is `['--help']`. Explicit later
server arguments, including `nogui`, may use the same bounded format; the model
allows at most64 arguments and65535 total UTF16 units and rejects credential
options. It does not read accounts, accept an EULA, select an existing world, or
write a Java object. The owner must keep its working directory and world tests
inside the authorized isolated project output.

## Native wiring

Append one managed argv root after the five primordial roots and the optional
child Thread root. Thus its byte offset is40 without a child and48 with one.
Increment the actual normal root-span count and include this extra root in
snapshot/teardown inputs. Define these macros in the owner:

| Macro | Value |
| --- | --- |
| `ORIGINAL_GAME_MAIN` | `model['symbol']` |
| `GAME_MAIN_CLASS` | `boom_class<model['class_id']>` |
| `GAME_ARGC` | `model['argv']['argc']` |
| `GAME_ARGV_TEXT_ROWS` | `boom_game_argv_text_rows` |
| `GAME_ARGV_ROOT` | `boom_vm_thread_root_cells+offset` |
| `VM_LEVEL_CELL` | the existing source-derived VM.initLevel symbol |

Include `G.data(model)` and `native/entry/game_main.asm.inc`. Invoke the private
`boom_vm_call_game_main(Context32, report)` only after phase3 succeeded. Add
external procedures `boom_java_property_array`, `boom_java_property_copy`,
`boom_class_ensure32`, and the original Main symbol. Add external data
`boom_java_platform_properties_pool` and the normal Main class descriptor.
The existing level cell and root bank are already owner bindings. The argument
table is defined in the same object; do not declare it EXTERN as well.

The helper checks the original phase3 called/returned2→4 report and current
VM level4 before allocating. It uses the real ABI2 properties callbacks to
allocate a normal source String[] and source String objects. It publishes the
array root immediately after allocation, so partially filled argv remains
normally rooted if a later allocation fails. Every element store and the root
publication executes in ASM. It then calls normal `boom_class_ensure32` on Main;
only a successful original initializer permits the original main invocation.
The root remains live until owner teardown.

Existing pending Context bytes are not changed. Allocation, initializer, and
main failures propagate their Context/pending value. The report captures the
latest Context16; it does not replace an exception with a fabricated success.
The helper returns EAX1 only after main returns with Context.kind0.

## Report576 / ABI14

The entire544-byte prefix is preserved. New DWORD fields are:

| Offset | Field |
| --- | --- |
| 544 | original Main class initialized |
| 548 | original main called |
| 552 | original main returned normally |
| 556 | argc |
| 560 | latest game Context kind |
| 564 | PC |
| 568 | method |
| 572 | depth |

The owner selects576/14 whenever a game entry is requested, calls the helper
after phase3, and sets entryComplete72 only for the final requested entry's
normal return. argc is stored after the phase3 gate, before allocation; if the
phase3 path fails and never invokes the helper, all new fields remain zero.
Class initialization may fail before main_called, while a partial argv stays
rooted for orderly shutdown and exact source diagnostics.

The existing phase2 latest-main capture at296 now includes game/Logger errors.
The phase3 Context at528 remains its earlier snapshot. With a game request,
phase3 success must use its own called/returned/2→4/Context0 fields; do not force
it to equal a later exceptional main Context. Compare game Context560 with the
latest-main capture when the helper ran. A source row during Main `<clinit>`
must be reported even though main_called remains false. Preserve all native
owner/worker/cleanup checks. The new report is not permission to mark help,
world creation, or complete gameplay successful without their own evidence.

## Validation and current limits

`.boom/game-entry/static-v149-a/verification.json` seals the original source
model, actual ML64 assembly/object, imports, argument data and FRAME unwind.
It deliberately records `linked=false`, `executed=false`, `help_executed=false`,
and `current_source_selection_Main_selected=false`. The static object references
the real dynamic source main/class symbols; it does not supply a replacement
implementation. Fourteen focused tests pass, including real ML64, exact UTF16,
empty/surrogate data, budget/credential rejection, selected-Code identity,
missing logger initializer and missing properties COFF rejection.

The shared prepare/build/verify/invoke tools now accept `--server-help` /
`-ServerHelp`. That request requires original Phase1/2/3, explicitly selects
Main and its original initializer, constructs argv in ASM, and retains the
additional argv root in the ordinary primordial span. The ABI14 decoder keeps
earlier System success separate from a later logger/Main failure. Successful
help output still leaves all complete-game/world flags false.

Root independently ran all fourteen focused cases and the combined 495-test
Python regression (11 skipped, zero failures). The complete shared emitter,
including both physical native root banks, normal source banks, six primordial
cells, phase owners, argument table, and new Main helper, was actually assembled
with matching COFF imports/exports in
`.boom/native-owner-emitter/game-static-root-v150-a/verification.json`.
That check is explicitly a static fixture, with no link or execution claim.

The fresh31 source preparation includes Main, its seven-byte original logger
initializer, the real properties COFF and both string-literal root exports.
Full source verification and actual Main execution remain separate pending
checks. No original Java Code, runtime572, provider namespace, or Java
initialization state is modified by this bridge. Isolated world startup and
final game acceptance remain outstanding.
