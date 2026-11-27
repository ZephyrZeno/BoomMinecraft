# Unregistered normal-array Inflater native slice

This page records the earlier standalone slice. The newer
[RW owner and original-Java API validation](INFLATER_RW_OWNER.md) has separate
ownership, source bindings, and actual execution evidence; it does not relabel
the older receipts below.

This development component implements the original `java.util.zip.Inflater`
native protocol for `initIDs`, `init(boolean)`, `getAdler`, `reset`, `end`, and
`inflateBytesBytes`. All execution is MASM, using the unchanged, separately
verified [raw streaming](DEFLATE_STREAM.md) and [zlib wrapper](ZLIB_STREAM.md)
objects. It is not a registered provider, completed Java Inflater constructor,
automatic Cleaner implementation, ZIP integration, or game acceptance.

## Locked source and protocol

`scripts/inflater-source.py` reconstructs all eleven original declarations,
native frame flags, error-field FMAPs, normal byte-array type, error constructors,
String layout, and class-initialization call sites from the locked original
class files. The Java sources are extracted under
`.boom/inflater-normal/pinned-sources`; the already pinned JDK 21 `Inflater.c`
is under `.boom/deflate-raw/pinned-sources`. These are checked against their
exact SHA256 values, including the original Java Code identities.

The normal `Context32` service receives the original private native argument
slots. A successful `inflateBytesBytes` result packs input consumed into bits
0..30, output written into bits 31..61, finished into bit 62, and needs-dictionary
into bit 63. Successful native calls leave the original `inputConsumed` and
`outputConsumed` fields unchanged; Java owns their ordinary public-wrapper
updates. A data error writes the actual per-call counts through the original
FMAPs and invokes the whole original `DataFormatException(String)` constructor.
Original Throwable initialization and `fillInStackTrace` run through the normal
source/provider path. The native message is the generic `Invalid compressed
data`, rather than zlib's individual diagnostic strings.

Input and output must be normal heap byte arrays with valid signed-int slices.
The private protocol has no end-of-input flag, so incomplete input pauses for
more input. Raw `getAdler` is zero; wrapped `getAdler` is the accumulated output
Adler, or the parsed DICTID while a dictionary is required. A dictionary request
consumes exactly the six-byte zlib header and returns bit 63; actual dictionary
installation is not implemented.

The five dictionary/direct-buffer native forms and overlapping array ranges
explicitly return Context 20. Malformed private handles/arguments return Context
7. No invalid private-pointer behavior is claimed equivalent to the JDK. The
frozen cores' two known differences remain: RFC HDIST 31/32 headers with unused
reserved symbols are accepted here but rejected by the JDK, while distances
beyond a small CINFO window are rejected here even when the JDK accepts them.

## Ownership and actual image

The INFL128/1 pool publishes monotonically increasing, nonzero handle tokens.
A shared lifetime lock covers lookup and every live-node operation; each node
also has an exclusive state lock. `end` takes the lifetime-exclusive lock,
unpublishes the node, then frees it. Lookup precedes any node-pointer use.
Native nodes hold only primitive decoder state, a 32 KiB history, locks and
ownership records, with no managed oop roots. No lock spans a Java error
callback. `boom_inflater_close_owned` is explicit test/VM-owner teardown;
executing the original Java Cleaner is not inferred from it.

The candidate verifier checks the current 107-tool source identity, original
65-slot batch/full proof, Frame8, source declarations and current 31 provider
receipts. It independently assembles the exact candidate text and compares
non-debug code/data, symbols, relocations and unwind information. The candidate
is outside the original full source-selection proof.

The component consumes an immutable, independently reverified focused source
envelope: 676 normal classes and 2638 Java methods, including the actual DFE,
OOME, InternalError and Throwable callbacks. It removes only the eleven exact
native fail-only PUBLIC/complete PROC definitions. Original diagnostic rowdata,
all remaining Java code, other COFF inputs and the SHA572 runtime are retained.
The candidate and frozen raw/zlib objects are separate added link inputs. The
ordered canonical RSP, actual PE exports and input hashes are checked before
execution and again afterward. `full_selection_reverified=false` describes the
additional native overlay, not an exemption from verifying the original source.

## Executed scope

`.boom/inflater-normal/component-c/execution.json` is the complete direct-service
run, SHA256 `c925c0ff72a71763027348ddbc4691991803c98749028164d90fc750b3c797d1`.
It records:

- 182 valid raw/zlib streams, four actual typed data errors and five DICTID
  requests, with 306745 native calls including concurrent work. Every normal
  call checks packed counts, data, unchanged input, and untouched error fields.
- Whole original `Throwable.getMessage` and `String.toCharArray` observations
  confirm the real DFE type and complete message. The fixture normally runs the
  original String initializer first, from state 0 to 2. It does not write String
  flags or any class state. Inflater remains state 0 throughout this direct
  service fixture; its receiver is an ordinary allocated object, not a completed
  original Java constructor.
- Eight distinct OS workers run sixteen independent streams each. A real
  8 MiB stored-block copy overlaps `end`; the shared lifetime lease is observed,
  the copy completes, and the stale handle is rejected afterward.
- Quiescent GC uses the actual eight linked source root spans, collects 962
  objects, and preserves two live primitive-owned handles. Explicit owner
  teardown releases four abandoned states. Final native state and byte counts
  are zero, with allocations equal to frees.
- A separate tool-only JDK process constructs real Inflaters and invokes the
  original private native method through reflection, without field writes.
  All 196 reference cases pass, including 137630 calls, nine actual data errors,
  five dictionary requests, original packed counts and Adler/reset behavior.
  Neither this reference process nor a zlib DLL is used by the delivered ASM.

Four actual-COFF negative tests in `tests/inflater_native.py` reject a changed
service instruction, lifetime-lock relocation, original exception-constructor
pointer, and unwind data. The earlier `component-a`/`component-b` failures remain
historical. Their direct fixture invoked the String observer before normal
String initialization, selecting its compact-string branch too early. Their
original harness snapshots and failed observations are preserved; the fix only
adds normal original String class initialization to the test fixture.

## Original construction boundaries

Original Inflater `<clinit>` calls `ZipUtils.loadLibrary` before `initIDs`.
`BootLoader.loadLibrary` actually discards the `NativeLibraries.loadLibrary`
return value with POP. The current builtin library model has `net`/`nio`, not
`zip`; absence of that name alone is therefore not evidence of the first stop.

The separate owned `.boom/inflater-normal/constructor-prefix-b/execution.json`
runs the complete original System phases 1/2/3, reaches VM level 4, and then
enters normal Inflater initialization without this candidate. It actually stops
at `initIDs` 75476, diagnostic row 131972, before the original constructor body.
Both workers exit/reap normally, held monitors are zero and cleanup is 7. Its
execution SHA256 is
`2809a40f7c941747bc850ebede6f5923f11e0272d2d20790bb3a5661b8d0b153`.

An actual outer-adapter probe using the narrower focused component instead
stops in original Java initialization at unselected `Object.equals` 42389,
row 81940. `.boom/inflater-normal/normal-adapter-a/observation.json` retains
that distinct source-selection boundary, not a successful constructor claim.
The wider Main source envelope includes those methods, but lacks the normal
DFE class and constructor. A separate constructor-lifetime-only development
profile provides only `initIDs`/`init`/`end` against that wider source; its
unavailable DFE branch explicitly stops with Context20 and does not fabricate
class metadata. Its actual fresh native process completes original System123
to VM4, original Inflater initialization, the original constructor and original
`end`. The real Cleaner initialization adds a third source worker; all three
exit/reap, Reference stop tokens balance3/3, held monitors are0 and cleanup is7.
Original `end` already releases the native state; later explicit owner teardown
frees0. This does not claim execution of the inflate/DFE paths or automatic
Cleaner ownership completion. The first old two-worker assertion failure is
preserved rather than relabeled. The successful three-worker validator result
is `.boom/inflater-normal/constructor-prefix-c/recheck-a/execution.json`, SHA256
`b4e8e4bd336a7940716f717aabeee1e3b903ccf2e1c632f98306b33df701fca5`.

Root independently rebuilt the complete direct-service candidate against its
separately verified raw/zlib core and reran the full suite and JDK comparison.
Source proof `.boom/inflater-normal/root-review-source-v179-a/verification.json`
has SHA256 `d1dcb220080899c58c475dfaeed6b7f30b37b20bce2643c63eca5c881100acdc`;
execution `.boom/inflater-normal/root-review-component-v179-a/execution.json`
is verified with SHA256
`151acee7255058f7edb6326798f78c97a579d35b53d41e5b5bc763448bfbf4d8`.
All four actual-machine mutation tests also passed. A separate root cold
replay of the sealed three-declaration constructor executable passes every
source/COFF/LINK, original Java, three-worker and cleanup check:
`constructor-prefix-c/recheck-root-v180-a/execution.json`, SHA256
`eb46183d890cc43351da4c3e8662099c7667b160897b01cf548f8ee7dca9cb4b`.
The complete direct service and the narrower original-construction profile
remain distinct; neither is registered or a full game acceptance result.

## Reproduction

Use a fresh output directory for every build and execution, retaining any first
failure. With the current frozen 107-tool inputs:

```powershell
D:\Dev\Python312\python.exe -B scripts/inflater-candidate.py build --state .boom/formal-native-transitions/manifest107-31-v157-a/pending-state.json --core .boom/zlib-stream/source-b/candidate.json --output .boom/inflater-normal/review-source-a
D:\Dev\Python312\python.exe -B scripts/test-inflater-normal.py build --candidate .boom/inflater-normal/review-source-a/candidate.json --envelope .boom/inflater-normal/focused-envelope-a/source-envelope.json --output .boom/inflater-normal/review-component-a
D:\Dev\Python312\python.exe -B scripts/test-inflater-normal.py execute --images .boom/inflater-normal/review-component-a/images.json
D:\Dev\Python312\python.exe -B -m unittest tests.inflater_native -v
```

`prepare` can build a fresh original focused selection if needed; its current
full proof is reused through `existing-source-selection.py`'s immutable sealed
chain without re-running a large selection for each independent native overlay.
The source-pending 31-provider input is not promoted to runtime acceptance by
this test.

| Evidence | SHA256 |
| --- | --- |
| source-b/candidate.json | `b745c9f051ad1654960cccc28901b1b9eedc8fcf0ab005a957ea0b059bcedf11` |
| source-b/verification.json | `3c6b00899a318a4855844343c41df5baa3b490abe7484576e5e1bb2326d7f83b` |
| focused-a/selection/selection-verification.json | `450f102e0f78528c4c4b2845825ef9869c332ff9c9fec32b65fa944bebed8a06` |
| focused-envelope-a/source-envelope.json | `6125c2ef57e354b7ef65100c286526782201cbe9606d93ec0be86f87a4784874` |
| component-c/images.json | `1458023dd397b0752ebba9b009e89ee0922ee169034e56d8fc110086898897b1` |
