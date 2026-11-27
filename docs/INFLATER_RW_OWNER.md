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

An actual 228-object assembly component completed System initialization phases
1, 2, and 3 and used the real primordial thread. Fourteen original-Java cases
executed 14 constructors, 147 public inflate calls, two private error calls,
and 28 `end` calls including repeats. Empty, stored and fixed streams, fragmented
input/output, reset/reuse, consumed counts, Adler values, exception types, and
cleanup matched the locked JDK reference within those cases. All twelve cleanup
observations passed; the final native root snapshot contained 2,523 references.

Exact error-message comparison still has four differences across two malformed
stream types: the candidate returns `Invalid compressed data` where the
reference returns `incorrect header check` or `invalid block type`. The overall
exact comparison remains false. The successful normal-behavior checks do not
establish complete zlib, Inflater, concurrency, or game compatibility.

The original server `Main --help` image subsequently passed source, complete
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
