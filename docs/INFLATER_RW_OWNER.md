# Inflater arrays with tracked native memory ownership

The current Windows x64 candidate runs the original JDK `Inflater` constructors
and Java wrappers over a MASM decoder owner. It remains outside the registered
35-provider set. Full Minecraft startup, the client window, and a world are not
verified.

The source fragments are
[the owner](../native/kernels/inflater_rw_owner64.asm.inc),
[field registration](../native/providers/inflater_ids.asm.inc), and
[the service](../native/providers/inflater_rw_service.asm.inc).
[INFL256/2](../native-config/inflater-rw-abi.json) specifies their shared layout.
The service uses the separate
[raw reason decoder](../native/kernels/deflate_stream_reason64.asm.inc) and
[zlib reason decoder](../native/kernels/zlib_stream_reason64.asm.inc), under the
[reason ABI](../native-config/inflater-codec-reason-abi.json).
The generated headers supply actual source-derived Class, FieldID, FMAPPROC,
native Frame32, type-map, and exception-constructor bindings. These fragments
contain no fixed Java method IDs or local build paths.

## Ownership and execution

| Structure | Bytes | Purpose |
| --- | ---: | --- |
| Pool | 256 | Registry, field caches, and decoder-owner state |
| Stable record | 256 | Opaque handle, generation, and persistent Core job |
| Borrow | 64 | Checked native decoder access and release result |
| Decoder allocation | 34,608 | Raw or zlib state owned by the common RW allocator |

The record table is native metadata. Allocations use the assembly RW owner's
allocate/free and borrow/release operations. Each handle is checked before its
allocation can be dereferenced. A free job stays in the stable record rather
than the allocation it frees. Failed frees or releases retain ownership for
cleanup; callers preserve the VM if cleanup cannot finish.

`initIDs` validates and caches the actual `inputConsumed` and `outputConsumed`
field operations. Array inflation uses those cached operations, releases every
native borrow before invoking Java, and constructs real Java exceptions.
Successful calls preserve Java's public-wrapper accounting. Native error calls
write the per-call counts expected by the original Java catch path.

Supported operations are `initIDs`, `init`, array-to-array inflate, `getAdler`,
`reset`, and `end`, within the ordinary heap byte-array and valid signed-slice
domain. Dictionary setters and the three direct-buffer inflate forms remain
explicitly unsupported. Automatic or moving collection and arbitrary forged
private pointers are outside this candidate's verified scope.

Shutdown first quiesces Java, workers, and library users. Query and RAF I/O
services drain before the Inflater and Perf owners; root snapshots, registry,
frames, heap, and the common RW owner follow. No Java callback runs while the
decoder's native locks or leases are held.

## Actual verification

The current source epoch verified 8,656 classes and 71,776 Java methods. All
previous 71,775 method rows stayed identical; only the original
`DataFormatException(String)` constructor and its class were added.

An actual 230-object assembly component completed System initialization phases
1, 2, and 3 and used the real primordial thread. Fourteen original-Java cases
executed 14 constructors, 147 public inflate calls, two private error calls,
and 28 `end` calls including repeats. Empty, stored and fixed streams, fragmented
input/output, reset/reuse, consumed counts, Adler values, exception types, and
cleanup matched the locked JDK reference within those cases, including all
compared error messages. All twelve cleanup
observations passed; the final native root snapshot contained 2,523 references.

The earlier generic-message candidate remains historical. Actual FCHECK failure
now selects `incorrect header check`; reserved BTYPE selects `invalid block
type`; an invalid stored LEN/NLEN pair selects `invalid stored block lengths`.
The original-Java 14-case run has no remaining comparison differences. Other
malformed-stream reasons still use the generic message, and dictionary/direct
buffer support remains incomplete. These cases do not establish complete zlib,
Inflater, concurrency, or game compatibility.

The reason-aware entry points use Job96 with a four-byte reason output at byte
92. Their private persistent reason cells use raw-state byte 140 and zlib-header
byte 72; the state allocation sizes stay unchanged. The original codec objects
remain linked for the existing owner's reset operations, while the service
calls the new step entry points. This avoids changing the old Job80 entry point.
The published fragments rebuild to the complete COFF of the actual executed
units, including all nondebug sections, symbol auxiliaries, relocations, and
unwind data.

Separate native regression covered 324 sequential cases, including 247 invalid
FCHECK values, plus 256 cases across eight distinct OS threads synchronized by
a barrier. The 8,768 codec calls preserved the old codec's progress, output and
state outside the new reason cells; terminal retries and the original resets
also passed. That decoder-only test is separate from the original-Java run.

A separate original server `Main --help` image passed source, complete
COFF, canonical LINK-response, import-policy, and whole-PE relink checks. Its
actual process advanced beyond `Inflater.initIDs` and stopped at the missing
`java.lang.reflect.Array.newArray(Class,int)` native binding. System reached VM
level 4; Main class initialization, its body, and help output did not complete.
Three workers were reaped. The common RW owner recorded six allocations and six
frees, with zero final leases, live allocations, logical bytes, and metadata
bytes. This remains a diagnostic prefix rather than a game startup result.

Local execution receipts and one-off orchestration stay in ignored `.boom`.
Only reusable assembly sources and the ABI are published here. The earlier
[normal-array slice](INFLATER_NORMAL.md) retains its separate historical scope.
