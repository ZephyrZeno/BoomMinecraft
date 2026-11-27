# Normal batch LambdaMetafactory expansion candidate

The original strict `ModuleDescriptor.Builder.packages` now executes its real
`invokedynamic` at method 49915 / PC 17 in an isolated ASM image. The unchanged
public `ModuleDescriptor.newModule` → strict `packages` → `build` chain completes.
This is a compiler-owned expansion experiment over the historical 64-slot / 26
provider source selection. It is not a production batch receipt, a complete
LambdaMetafactory implementation, or a Minecraft startup result.

The current 1.21.1 native Main experiment has now reached a logging-library
lambda after bulk selection of 9,640 existing generated logging methods.
The new source full verifier covered 81,476 original Java methods, and the
241-object native image passed independent complete PE relinking. Actual
execution stopped at diagnostic row5173, kind45057 and natural exit86:
PropertiesUtil class52039, its original class initializer method510874 at
PC0, CP328, invokedynamic descriptor `()Ljava/util/function/Supplier;`.
The original log4j-api 2.22.1 Class SHA is
`d4903a1673e427e10c353be7502ba0920e2c90b3f8b061f57b1600ceb217d96d`.

Independent original-Class/BootstrapMethods decoding identifies zero
captures, erased `Supplier.get()Object`, instantiated `()PropertiesUtil`,
and the same-host private static synthetic implementation method510873,
`lambda$static$0`. The existing static-reference source rule accepts this
site. The original target, Object constructor and LambdaMetafactory class
initializer are already selected in the current source.

A subsequent single-site derived image now includes the generated class
109945 and methods530837-530839, the extended sparse metadata consumers,
the generated-class failure root, and the host protection-domain mapping.
The original Java Code and metadata prefix remain unchanged. Its 242 actual
objects, 14 root spans and five additional oop cells passed complete object
checks and independent full-PE relinking. The resulting PE SHA is
`643970256966d87d0000a0d794f83d6ae4608f8526bbca4961b25286aec9a530`;
the independent proof SHA is
`3d5243c1c0ca399c98207521ebba28a780a82719ce3be10149c00281f2a9eb44`.
This is an explicit local derived candidate, not a shared production receipt.

Its actual owned native execution naturally exited70. System phase2 and
phase3 returned successfully, reaching VM4, but Main class initialization
did not complete and Main's body was not called. The latest Context is
kind20 / PC2 / method70790 (`AbstractQueuedSynchronizer.release(I)Z`);
this outer position is not a recovered dynamic Java stack or proof of the
first failing callee. One monitor acquisition remained, cleanup flags were0,
and teardown error170 caused the unchanged canonical decoder to reject the
run. The JMAP256 and NMWO320 resource parsers also rejected incomplete cleanup.
All 1,160 pinned inputs and the 117 formal tool sources were rechecked unchanged.
The raw observation SHA is
`abe9a50a353ecaa7cab5f038c068b9a716c0da47399117a53a787c559a5c25ce`.
No current-program lambda factory/SAM execution is established by these reports.
The earlier exit86 run passed its cleanup checks; the later exit70 run did not.
Main initialization, its body, help output, the client window and a playable
world remain incomplete.

A hardware Context20 watch on a fresh byte-identical image located the
first failure inside `boom_windows_nio_dispatcher_init_ids`, through the
original `WindowsNativeDispatcher.<clinit>` callback. The actual linked
UFMP2 header had capacity109946 while the WNID guard expected109945. One
static scan also found the equivalent RFID and INID guards. Three derived
registry objects now each change exactly one source constant and one machine
immediate to the actual capacity; their other code, relocations and unwind
metadata remain equal. The updated whole-PE proof SHA is
`9ab75f518d4b4b0c110cbfd33437ada32a07515bc834b3fcfcf6a2e33d6d3cda`.

The subsequent native execution naturally exited86 with diagnostic row110111
for the original protected native `Object.clone()Object`, method42390. It is
a native declaration gap, not a Java method that can be source-admitted.
System123/VM4 and all strict heap/thread/JMAP256/NMWO320 cleanup checks passed,
with zero held monitors and cleanup flags7. All image inputs and 117 source
tools remained unchanged. The execution SHA is
`87eec9f4fe9bed3547ed2ba61b45e1c87b9ba6ce47a74b5a2a090d4140727a0d`.
Main initialization and its body still did not complete; no game startup is
established. The earlier failed records remain separate history.

The next derived image expands all 23 already verified static-reference,
zero-capture source sites together and adds the normal native
[Object.clone service](OBJECT_CLONE.md). It has 244 actual objects, 61 runtime
and metadata roles, the same 14 root spans, and 115 additional oop cells
(Class23/name46/domain23/failure23). The independent full-PE proof SHA is
`bfa1c258e1535daea304cca26102695854d30448750c2e987ed83c6f9c51d510`.
The generated range is types[109945,109968), methods[530837,530906); the
PropertiesUtil expansion is now type109961, not the earlier single-site ID.
One site has historical execution-stop evidence; the other 22 were selected
from source. Batch compilation does not prove all factories/SAMs ran.

Its actual native Main naturally exited86 at diagnostic row126316 for the
original native `MethodHandleNatives.resolve(MemberName,Class,int,boolean)`
declaration, method47023. These reports do not independently count clone calls. Heap,
registry, frames, thread owners, JMAP256 and NMWO320 cleanup passed again;
all input identities and the 117 source tools remained unchanged. The run SHA is
`ab1de92edc8cf5503b831976800d18dc36ba7d007dcd7de6d8b581d2b9d79822`.
Main initialization, its body and help output remain incomplete. This does
not establish client/window/world startup or game performance.

## Checking namespace capacity consumers

`scripts/audit-namespace-capacities.py` derives the type capacity from the
actual linked UFMP2 pool assembly, then checks every linked assembly unit's
`*_UFMP_TYPES` constant and its explicit pool+8 comparison. It accepts the
image manifest and its independent full-PE proof with explicit SHA bindings;
the sources must be pinned by both, and the actual executable, runtime and
object identities are checked. Original IDs and generated method IDs are not
treated as capacity constants.

```text
python scripts/audit-namespace-capacities.py --image <overlay.json> --image-sha256 <sha256> --proof <verification.json> --proof-sha256 <sha256> --output .boom/namespace-capacity-checks/review.json
```

The tool writes a fresh report under `.boom`, `target` or `dist`. Exit0 means
the recognized UFMP2 capacity guards match; exit2 reports stale guards. This
is a static build check, with no game execution or runtime acceptance. It is
separate from the 117-tool provider source identity and does not register a
new runtime provider.

The verified single-Lambda image before the three registry fixes produces
three stale guard findings and direct Python exit2; the repaired verified
image produces zero stale findings and exit0. These are actual image inputs,
with the same UFMP2 capacity109946, rather than synthetic constant examples.

## Generic source rule

`normal-lambda-source.py` reads the pinned original classfile, BootstrapMethods,
method handles, erased/instantiated method types, source implementation Code,
loader/module identity, and member access. The rule accepts the exact ordinary
`LambdaMetafactory.metafactory` protocol with a concrete static Java target,
reference arguments, required reference casts, exact primitive results, and
reference/void return adaptation. It does not select by caller name or method ID.
Cross-module targets, non-static handles, boxing, primitive parameters,
altMetafactory, serialization, bridges, ambiguous SAMs, and shared CP entries
used by multiple indy instructions retain explicit deferred reasons.

The writer emits real version-65 classfiles with its own `boom:` generated
origin, source host/Code/CP/PC provenance, a private constructor, `$capture`, and
the SAM. It never labels generated bytes as original JDK input. Its hidden-class
self references share the `this_class` CP Class entry; a duplicate nominal Class
entry incorrectly performs name lookup and is rejected by the JDK oracle.
The VM's hidden `Class.getName()` is separate from the nominal classfile name:
`<nominal dotted name>/0x<sparse type identity>`. The suffix is an identifier of
this VM, not a copied JVM address.

The ASM factory executes the original LambdaMetafactory class initializer and
normal generated-class initialization. It allocates a fresh normal object and
executes the generated constructor, including the original Object constructor.
The SAM performs its original erased-to-instantiated reference check, then calls
the original static implementation and adapts its return. Instance identity is
not cached; fresh allocations are allowed by the
[LambdaMetafactory contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html).
Hidden Class name/visibility rules follow the
[Class contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html).

Reference capture classfiles/ASM have focused writer/verifier tests, but the
current physical overlay explicitly rejects capture fields. Capturing UFMP
declarations and reflective metadata are not implemented by this overlay.

## Stable identities and physical overlay

Original classes, Java Code, arrays, primitive types, method/field IDs, Java
objects, and provider artifacts remain sealed. The first derived class/type is
109945, after the old type capacity. Its method IDs are 530837–530839, after the
original complete method inventory, not after the 501044 provided frame rows.
These numbers are this batch's evidence; the tools calculate every range from
the input summary/catalog.

`normal-lambda-overlay.py` reconstructs the original data range, requires its
exact presence, and derives these replacements:

| Consumer | Derived data |
| --- | --- |
| Runtime type map | Capacity, tail descriptor pointer, tail normal runtime row |
| JCLS / Class names | Tail Class root/record/name; original loader/module keys and canonical-name IDs retained |
| Unsafe bootstrap | Zero scale for the new non-array class and matching strict capacity |
| Unsafe field pool | Empty new-class field range and matching strict capacity; all original field declarations retained |
| Class lookup | Matching capacity and tail initializer map; hidden class omitted from `forName` names |
| Source frames | Three contiguous 32-byte rows with generated/hidden flags; original rows unchanged |
| Virtual dispatch | New receiver rows in every applicable selected shared table; original rows/constraints retained |
| Diagnostic object | Only the exact source indy category-3 procedure removed; original row data/complement preserved |

The generated descriptor is the actual 64-byte normal ABI2, initially cold0,
with a real initializer and cause-root pointer. One explicit contiguous failure
root bank is emitted. No host writes initialize Java classes or fields.

`verify-normal-lambda-expansion.py` independently checks classfile instruction
semantics, including the original target, cast, capture order, and discarded
return. `verify-normal-lambda-overlay.py` rebuilds source ranges, checks real
COFF exports/imports, old `.text` bytes and code relocation targets, actual
type/Class/dispatch cells, root spans, contiguous frame positions, and generated
FRAME unwind. Native/data-containing units are reassembled; ordinary selected
Java COFF is reused without regeneration.

## Actual evidence

All paths below are ignored project outputs, not files required in git.

| Evidence | Path | SHA-256 |
| --- | --- | --- |
| Source/classfile semantics | `.boom/lambda-expansion/strict-builder-source-v147-h/source-verification.json` | `593661e375d8da1e238edf8212ac03bcc7458d1658d2723ebf01a7665ffa6b44` |
| Actual sparse COFF data / code preservation | `.boom/lambda-expansion/strict-builder-overlay-v147-f/verification.json` | `7657e3e2478e877941894094f63f37c7e92c9c9d00a68d413bf97cec4a2dacc2` |
| Cold ASM component execution | `.boom/lambda-expansion/strict-builder-execution-v147-h/execution.json` | `1655d03b666c470b9ddfab778622232e94ce764b908f3cadb4855b96070bb966` |
| Same generated classfile, development JDK | `.boom/lambda-expansion/strict-builder-oracle-v147-c/verification.json` | `66f140fb3fe44e113f358ed097e7e23a05004080bb8477110939114cabf97abc` |
| Five resealed COFF semantic rejections | `.boom/lambda-expansion/metadata-negative-v147-a/result.json` | `689bbec6efaccc7ff2869a18d6d3861d1e2cc13e2f591cf9efd0947a306b1bec` |
| Automatic source expansion | `.boom/lambda-expansion/automatic-source-v147-b/source-verification.json` | `22267dba18d615e26ee937ac0ca6611479e2d785c16afc7ecd77827511b7b3e7` |
| Literal-capacity consumer audit | `.boom/lambda-expansion/capacity-consumers-v147-h.json` | `a1edfe00d23a20b9e2435fc8a0b1579671c9ab5e2337f0124e36dd13bf748f8a` |

The ASM component executes 8 OS threads × 16 factory/SAM pairs, producing 128
distinct objects with cold normal initialization and balanced source frames. It
checks the normal runtime type, hidden Class/name, and host loader/module
**records**. Actual named Module oop publication is not executed in this fixture.
It verifies a real Object→String wrong-class fault (Context12 at generated PC2),
null receiver NPE boundary (Context4), and the original Checks null-argument
typed IllegalArgumentException (Context16). Existing pending Context bytes stay
unchanged through constructor/factory/SAM. The original implementation returns
the same non-null String while the void SAM returns zero.

Two explicit quiescent collections scan 1183764 cells in ten ordinary/root
spans and free 784 then 5 objects. The first retains the generated object through
an original HashSet graph and one declared test handle; the second drops that
handle and reclaims it. Its Class mirror survives through the ordinary JCLS
root. Heap destruction succeeds. This does not claim automatic concurrent GC,
unloading, captured-field GC execution, or full VM exception materialization.

The development JDK defines the same classfile as a hidden nestmate of its
original lookup host. Its seven cases cover valid/Unicode String inputs, wrong
class, null argument, null receiver, invalid package, and the original strict
Builder chain. Unicode here is JDK oracle coverage, not an additional ASM input
claim. No JVM participates in guest execution.

All five resealed actual-COFF negative cases pass. The runner changes capacity, Class root count,
host Module ID, generated frame Code length, and dispatch receiver while updating
their artifact digests. The full verifier must reject the semantic cell, not
merely a changed file hash. The nine small unittests pass and check capture order,
POP/POP2/IRETURN, hidden self-reference/name invariants, and resealed classfile
cast/target mutations.

Earlier failures remain in their original directories, including Unsafe's old
capacity mismatch, the hidden nominal CP self-reference failure, and the first
test's incorrect assumption that a null argument to Checks must throw NPE.

Root independently reconstructed the source, all physical overlay units, and
all 317 automatically matched source expansions in
`.boom/lambda-expansion/root-review-v149-a/verification.json`, SHA256
`debe4d1fb60bf05b85424c171e20a051beee13d86ec6e022752737975596e01a`.
A fresh cold ASM run, `.boom/lambda-expansion/root-review-execution-v149-a/execution.json`,
SHA256 `c8baa4f75c99305dab28f2392e582aba065b4e2d8816a9e78c65d014c2e512b1`,
and a separate same-classfile JDK comparison,
`.boom/lambda-expansion/root-review-oracle-v149-a/verification.json`, SHA256
`cd3f7515e1fe35706d235253408ef25e6df73aa89827f153708bc0e57341894f`,
both pass. The nine focused unit tests also pass independently. These remain
the historical 26-provider/64-slot component scope described above.

## Bulk discovery and next production integration

This command selects original indy diagnostics by their pinned bootstrap,
signatures, access, and supported shape:

```powershell
D:/Dev/Python312/python.exe scripts/discover-normal-lambda-expansion.py `
  --selection <normal-source-round> --output <fresh-.boom-directory>
```

The old26 source selection yields 317 supported noncapturing source shapes, 976
deferred LambdaMetafactory sites, and 95 other protocols, across 1388 original
indy sites. All 317 generated classfiles pass independent source/bytecode
verification. They have not all been linked or executed. Required Java target
and bootstrap-class dependencies are listed; normal source admission is not
silently bypassed. `--assembler <ml64.exe>` also assembles the generated adapter
unit. Explicit `normal-lambda-expansion.py --site loader:class:CP` remains useful
for isolated witnesses.

The current production parent is the fully verified 65-slot batch
`.boom/named-module-batches/v148-jdwp-production-b`, summary SHA
`271870db974403d34343f7218a781e118caeef3bf79c3b18188df992a3f17056`.
It retains old slots0–63 and appends jdk.jdwp.agent at64; its Class root count is
110013 before any lambda expansion. The same discovery/overlay helper reads
`summary.class_literals.modules`, `loader_keys`, shape, and rows dynamically,
reconstructs that whole original pool, then appends type/Class roots. It must not
drop slot64 or reuse an old64 receipt. A future 65+one-lambda pool therefore has
110014 Class/loader/module roots. This document's actual component execution
remains old26/64; it is not evidence of a 29/65 overlay execution.

Production integration still requires explicit shared support:

1. Add a generated sparse catalog/origin store before normal closure selection.
   Preserve every old class/array/primitive ID; do not append to the old dense
   class vector in a way that renumbers its arrays. Implementation entry points
   are `batch_compile.rs`, `batch_catalog.rs`, `batch_types.rs`,
   `batch_dispatch.rs`, and a new expansion/lambda adapter module. No Rust file
   or compiler executable was changed by this candidate.
2. Teach the resolver/prepare/verifiers to consume that explicit derived lineage
   and generated classfiles. Current original-only `verify-batch-classes`
   correctly rejects generated classes; the candidate receipt is not a substitute
   for full production verification. Retain ordinary original source/provider
   verification and admit required Java dependencies through the normal graph.
3. Extend five selected provider source models before accepting a full new
   namespace: `class-flags-v1` (generated raw/modifier row),
   `normal-constructors-v1` and `normal-constructor-invocation-v1` (the real
   generated private ctor/descriptor and source rows),
   `normal-unsafe-class-initialization-v1` (capacity/new descriptor), and
   `normal-access-context-v1` (host protection-domain provenance, class roots,
   and generated method/caller metadata). Their old literal capacity is retained
   in this bounded fixture. This is an explicit production blocker, not proof
   that all Class/reflection/caller operations support the new type.
4. Include every actual replacement/adapter object, source model, dependency,
   frame row and additional root span in canonical RSP/manifest/proof inputs.
   Rebuild/verify provider metadata against the derived source namespace; never
   disable current-source checks or claim an old accepted pack covers it.

The standalone `prepare`/`assemble`, source verifier, overlay recipe/emitter, and
physical verifier can be reused by the future shared path. Its shared resolver,
generated reflection/protection-domain models, mod-transform invalidation,
unloading, general MethodHandle/constructor references, and complete bootstrap
linkage-error handling are not yet integrated. No shared registry, TOOL_FILES,
runtime572, accepted directory, Java class initialization state, or old original
Java Code was edited by these twelve new files.
