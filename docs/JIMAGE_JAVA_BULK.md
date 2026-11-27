# Original Java JIMAGE bulk-consumer probe

This probe has completed actual joint execution. It consumes a frozen,
successful NIO scalar image; it does not rerun or replace the large original
source verifier. The current NIO source selection already independently
verifies 8583 classes, 71603 Java methods and 192236 assembly functions. Its full
proof has SHA256
`e45acae7e9998b002714c01b760589b787a34ff86d04889585d791a16e5c60e5`.

The complete original ByteBuffer.get/getArray, ScopedMemoryAccess.copyMemory,
Unsafe.copyMemory and all modeled Java input-check methods are selected with
matching class and Code hashes. The no-copy baseline retains the sole relevant
unprovided declaration: method 113559, diagnostic row 51673. The positive image
provides that original native after the NIO fixture's real scalar route passes.
The independent AtomicLong overlay has now passed the original cold
initializer, real long/long buffer constructor, 8 OS threads / 512 lookups,
four collections and full cleanup in
`.boom/jimage-native-map/atomic-baseline-v189-c/execution.json`
(SHA256 `2d2a2ca6025112c780ef035f880624d0b0f05f35929db8fc755aeb48ad25a267`).
Its original typed Unsafe unit still rejects the mapped getInt read. This is
the preserved baseline; it is not a scalar-read success. No class state or
mapping metadata is patched to bypass that prerequisite.

`scripts/test-jimage-bulk-consumer.py` builds two new derivatives. The first
retains every original object and should expose the actual copy-native stop.
The second removes only that exact fail-only PUBLIC/complete PROC, retaining
all diagnostic rowdata and every other function, and adds the independently
verified [native copy slice](JIMAGE_UNSAFE_COPY.md). Owner, library, hardware
capability, scalar, Java/metadata and lifecycle inputs are retained from the
successful baseline.

The already-selected APIs get(byte[]), get(byte[],int,int),
ByteBuffer.position(int) and Unsafe.getUnsafe currently lack PE exports. New
canonical RSPs add these four observation exports separately from the single
native-stop replacement. Original Java methods implement position changes and
restore the original position; host code does not write Java fields, create a
fake receiver, or alter a root bank. Destination arrays come from the original
ASM array allocator.

The host execute function is explicitly derived from the frozen NIO runner.
Its first validator is replaced with the stricter combined-image validator and
one bulk_probe call is inserted after the original getInt observation. The
function is renamed. Removing precisely those declared changes must recover
the original complete AST. Original worker, quiescent-root, collection and
cleanup statements are unchanged. This is a new reviewed harness, not a claim
that the original test function executed without modification.

The actual pure-leaf diagnostic object legitimately has no unwind sections.
The separate `scripts/diagnostic-leaf-machine.py` helper pins the complete
owner reader's file and function AST,
and removes only the final owner-specific unwind-table requirement in a private
namespace. All other header, section-flag, symbol/aux and relocation checks
remain intact. Source and exhaustive machine decoding must independently show
no calls, stack accesses, stack adjustments or nonvolatile writes. There must
be no imports; all jumps must be direct branches to instruction boundaries in
the same code section. Actual and newly assembled canonical complete
normalized COFF must match. All ordinary native/adaptor
objects keep the unchanged owner verifier with mandatory unwind checks.

Static preflight has actually reassembled the 117873521-byte derived stop source
and decoded 2526990 code bytes / 399013 instructions. Its evidence is
`.boom/jimage-bulk-consumer/stop-preflight-a/leaf-verification.json`.
The initial owner-domain unwind rejection remains preserved and is not
described as an owner-verifier defect.

The first independent-helper preflight is retained as historical evidence.
Independent small MASM fixtures subsequently exposed far-return, LOOP target
and branch-relocation checks that its first version omitted. The corrected
helper explicitly accepts only plain RET, checks relative loop branches and
rejects all relocations overlapping any branch instruction. The exact
canonical stop source has 265972 code relocations, all outside branch bytes.

The corrected independent helper was checked against another fresh MASM assembly
of those exact source bytes. Actual and canonical complete normalized COFF
matched, including all code/data, flags, symbols/aux records and relocation
targets. All 132999 jumps were local direct branches to decoded instruction
boundaries. The new evidence is
`.boom/jimage-bulk-consumer/leaf-helper-preflight-b/verification.json`
(SHA256 `0a5a76390cad3abf1bb8592093eb3431bbfdf47d676f907bce0202d11822295f`).
That helper has no dependency on the bulk test runner and is not
part of the shared 107-tool provider namespace. Its APIs are
`leaf_stop_coff(object, source_bytes) -> (normalized, leaf_proof)` and
`verify(actual_object, canonical_object, source_bytes) -> comparison_proof`.
Callers must separately prove the exact original stop-source removal and
fresh canonical assembly; the helper does not authorize source changes.

Root independently repeated all 14 machine tests and another full MASM build
and comparison of the 117 MB source. Its proof is
`.boom/jimage-bulk-consumer/root-leaf-v195-a/verification.json`
(SHA256 `05da3f82ca735fc2bbce16640de1338193b335fb636c05d147b76d904c925e49`).
The helper and its tests were committed separately as `597e8a8`.

The new consumer pins the independently frozen NIO extension verifier
`.boom/run-jimage-native-extension-v190-b.py`
(SHA256 `74d7463fb9c3217e10c865163d88940fcbc51a65cb45f3b55ffcef61ce10c35b`).
It pins that reader, its exact template, original NIO source and leaf helper
before importing them, and calls the complete `verify_images` chain with all
sealed inputs checked before native execution, including AtomicLong, scalar, map/library,
source/frame, ordered COFF and PE checks. Images cannot select a new reader
for themselves. The current remaining-stop object is found in the actual
ordered object list; same-named earlier sources in the parent input history
are not used.

The first baseline attempt stopped before linking or guest execution because
the new harness initially required equality between the pending state and its
accepted child envelope. That failure is retained in
`.boom/jimage-bulk-consumer/java-baseline-a-build.log`, with its original
producer snapshot `java-baseline-a-producer.py`. The harness now reuses the
frozen reader's exact source/provider/frame projection and accepted-parent-pin
check, preserving both original statuses and recording
`pending_scope_promoted_to_accepted=false`.

The corrected low-cost preflight was executed through the standard CLI before
the next full chain. Its proof is
`.boom/jimage-bulk-consumer/java-baseline-b-preflight/verification.json`
(SHA256 `6974603ad6152c942df26634676cd33e7b3c71d73a6b3acd428d7551b0a428ca`).
It independently checked the source method contract and threshold, exact
current stop, planned fail-only source removal, actual PE export difference,
unique PUBLIC definitions for all four observations, pinned reader/dependency
hashes and accepted/pending join. It performed no assembler, linker, Java or
expensive native-source/frame verifier work. The build CLI performs this
preflight first; the complete native-source/frame verifier still runs before
linking or executing the derivative.

Root executed `java-baseline-b` without the copy implementation. The actual
original Java path stopped at native113559 / row51673, Context
`[45057,59,52874,0,0,0,0,0]`, with complete cleanup. Its
`bulk-execution.json` SHA256 is
`dfea49cb973f2e2fdba09e2706d1521aea1f670f673ba2239150d4b630e47183`.
This receipt intentionally has `verified=false` and
`expected_copy_native_stop_observed=true`; the CLI accepts only that exact
expected baseline result.

Root then built and ran `root-java-copy-v201-a`. Original get(byte[]) passed
at 0, 1, 2, 6, 7, 512, 65536 and 4096 bytes, including the small scalar path,
the first copy-threshold crossing, interior data and the end of the mapping.
Original get(byte[],3,13) preserved surrounding destination bytes and advanced
the original Java position correctly. Original Java setters restored position;
the limit was unchanged. The actual normal native Frame8 adapter also preserved
all 32 pending Context bytes with the real Unsafe receiver.

All original worker, quiescent-root and cleanup AST statements remained equal
to the frozen NIO template. Eight OS threads still completed 512 original
mapping/construction/scalar calls; four GC passes freed `[1152,0,1,1]`.
Every worker, handle, mapping node, lease and module pin closed normally.
These concurrent calls exercise the retained NIO suite; this receipt does not
claim that the additional Java bulk cases themselves ran concurrently.

| Positive evidence | SHA256 |
| --- | --- |
| root-java-copy-v201-a/bulk-execution.json | `1d90a9eb668a77598994266fc072fb4240f3c8fe3b6c682df9b1bd04cbde288e` |
| root-java-copy-v201-a/bulk-observations.json | `701f1281e182b14a5949ecbc9083f95c632f352f0c64a52c5577dbf29a02051b` |
| root-java-copy-v201-a/execution.json | `536699d59e09fd333f5683329dd50658e3d9366689e76668ee3f79509feb31ee` |

The positive run used an isolated harness byte-for-byte identical to the final
repository script (SHA256
`7682ed9bbfb92e66fc3d2eacd3e7a9a5d661e3bef584792942789edc46d399f3`).
Its only change from the preserved baseline harness is the explicit two-function
Win32 shared-lock import allowlist when reading the already verified copy core's
symbols. The core's exact imports remain heap_contains and those two locks.
No runtime implementation or source Java changed for this test-driver fix.

This verifies the combined original Java bulk consumer for the listed cases.
It does not register the provider, extend original full-V scope to extra native
objects, implement arbitrary off-heap access, finish Main or start Minecraft.

Use fresh isolated output directories when reproducing:

```powershell
D:/Dev/Python312/python.exe scripts/test-jimage-bulk-consumer.py build-copy --base-images .boom/jimage-native-map/atomic-scalar-v192-a/images.json --copy .boom/jimage-unsafe-copy/root-source-v186-a/candidate.json --output .boom/jimage-bulk-consumer/review-positive
D:/Dev/Python312/python.exe scripts/test-jimage-bulk-consumer.py run --images .boom/jimage-bulk-consumer/review-positive/images.json
```
