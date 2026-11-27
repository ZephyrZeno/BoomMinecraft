# Leased readonly JIMAGE scalar reads

This unregistered slice adds five plain typed Unsafe reads whose null base and
address refer to a live leased record in the actual
[JIMAGE mapping owner](JIMAGE_OWNER.md). It does not enable arbitrary off-heap
access. The existing runtime DLL, 107-tool namespace, Java class files and
production typed Unsafe module are unchanged.

## Actual original source route

The source model independently reconstructs the original class declarations,
Code hashes and call sites. For example, `DirectByteBuffer.getInt(I)` 53549 calls
its private `getInt(J)` 53547, which supplies the original null base to
`ScopedMemoryAccess.getIntUnaligned` 112880/Internal112881. They call original
`Unsafe.getIntUnaligned` 113517/113516, whose aligned/unaligned paths use the
original native Int, Short and Byte reads. The Long paths additionally require
Long; Char paths additionally require Char. The model discovers native method
IDs from names, descriptors, original access flags and the locked 42-native
inventory rather than hardcoding those example IDs.

The added domain is exactly operations 2/3/4/5/6: plain Byte, Char, Short, Int
and Long. Original native argv slots remain Unsafe receiver0, base8 and address16
in bytes. Byte/Short/Int results are sign-extended, Char is zero-extended, and
Long preserves all bits. Endian conversion, alignment decomposition, buffer
indexes, sessions and reachability fences remain original Java Code.

No volatile, reference, Boolean, Float, Double, write or CAS operation gains a
mapping domain. Their original routes remain unchanged. Normal heap operations
and the existing VM thread-ID counter delegate to the original
`boom_java_unsafe_memory`, including its original rejection behavior.

## Separate native kernel and typed route

`native/kernels/jimage_unsafe_read64.asm.inc` exposes
`boom_jimage_owned_scalar_read(Job48*)`. Job offsets are owner0, address8,
kind16 DWORD, reserved20 DWORD, result24 QWORD, status32 DWORD, reserved36 DWORD
and reserved40 QWORD. The caller supplies accessible, disjoint job memory and a
live aligned owner allocation. Status0 reads actual data;1 is outside a leased
record;2 rejects arguments;3 rejects owner metadata;4 is not-ready/closed.
Unusable/overlapping job memory is rejected without publishing output fields.

The kernel pins Owner128/1 and its immutable implementation SHA256
`a11b4253485a1463a4d737174fe49bdc4357a6047111798d5f05833580716635`.
It takes the owner's shared SRW lock, rechecks readiness and record metadata,
requires a positive record lease, checks address+width and view+length for
overflow, and requires the entire read inside one record. The physical load
occurs before releasing that same lock. Every locked error path releases it.
There are no Java callbacks, heap allocations, global mutable state or decoder
imports. The owner allocation must outlive all reads; its exclusive close
cannot unmap a view during the shared read interval.

The typed variant keeps two separate objects. `typed.obj` preserves all 84
original aliases and every byte of the 42 original adapters, their data and
unwind. Exactly five terminal external JMP relocations point to the new
dispatch. The other 37 routes are identical. `wrapper.obj` checks pending
Contexts before dispatch, uses the original UFMP and normal Unsafe receiver
validation, then invokes the scalar kernel. A miss restores the original
arguments and tail-jumps to the unchanged runtime service. It never invokes an
old failing operation and clears its Context afterward.

The bridge trampoline consumes the actual JMAP80/1 public pool
`boom_provider_jimage_native_map_pool`: ready state1 at24 and its normally
published Owner128 pointer at8. The candidate seals that bridge's source bytes
and ABI. It does not publish a shadow cell or manually write a bridge owner.
Full bridge/Java runtime success remains unverified in this standalone suite.

## Executed evidence

`.boom/jimage-unsafe-read/source-c/verification.json` independently verifies
current source/frame inputs, the frozen actual owner object, exact generated
ASM, complete nondebug COFF code/data/symbols/relocations/unwind, the original
native prefix, canonical LINK response and complete scalar/owner PE.

`.boom/jimage-unsafe-read/execution-a/execution.json` is verified with SHA256
`d1c47e14a6a8818f1de0f256181b75ec937d08bdb0c03a16eaf378cd898e33fa`:

- 26780 scalar calls read the real locked141325186-byte JDK image.5170
  signed/unsigned values match Python file bytes and a separate tool-only JDK
  mapped ByteBuffer oracle, including unaligned positions and the last valid
  location for every width. Unknown, partial, wrapping, unsupported-kind and
  unleased addresses are rejected. Job input bytes and canaries stay unchanged.
- 5170 calls through a test-only ASM observer retain the exact production
  scalar object and check eight nonvolatile GPRs, ten XMM registers, stack and
  two canaries.
- Eight distinct OS workers each make2048 calls while the original owner
  releases the live lease and closes its real mapping. Reads that succeed
  return the expected bytes; later reads reject the released or closed owner.
  Final owner state is2 with zero entries, leases, mapped bytes and handles.
- 704 actual protocol comparisons against the SHA572 runtime check all eight
  Context DWORDs for pending errors and invalid typed metadata. The new
  five-argument service and trampoline match the original service. This fixture
  links the actual cold bridge data, leaves it cold, and does not claim a valid
  Java Unsafe receiver or normal buffer execution.

The early source-a tool-artifact reader and source-b SDK path-spelling failures
remain in their own directories. Neither published a verification receipt.
Source-c fixes only the candidate tool checks/canonical absolute library path;
the actual scalar and typed route algorithms did not change.

Five actual typed-COFF negative cases reject an adapter instruction change, a
write retargeted into the read profile, an omitted required read route, a
substituted original Unsafe class relocation, and changed original unwind.

Current scope still has `valid_Java_Unsafe_receiver_executed=false`,
`original_Java_DirectByteBuffer_execution=false`,
`bridge_runtime_binding_verified=false`, `registered=false` and
`full_selection_reverified=false`. NIO's independent original getNativeMap /
DirectByteBuffer source component must verify that combined runtime path.

## Reproduction

Use fresh directories and keep first failures:

```powershell
D:\Dev\Python312\python.exe -B scripts/jimage-unsafe-read-candidate.py build --state .boom/formal-native-transitions/manifest107-31-v157-a/pending-state.json --owner .boom/jimage-owner/source-b/candidate.json --output .boom/jimage-unsafe-read/review-source-a
D:\Dev\Python312\python.exe -B scripts/test-jimage-unsafe-read.py --candidate .boom/jimage-unsafe-read/review-source-a/candidate.json --output .boom/jimage-unsafe-read/review-execution-a
D:\Dev\Python312\python.exe -B -m unittest tests.jimage_unsafe_read -v
```

| Evidence | SHA256 |
| --- | --- |
| source-c/candidate.json | `1663ab0e1b7d77bb880da3f429933ec18dbeaf38668a4682338c459ca5a4c42e` |
| source-c/verification.json | `0f636ab18fa083aed88bfaa4317fc317adee46f0758407df865b5ed63a6173c7` |
| execution-a/ABI-probe/verification.json | `4aec0c6935a0151d8dbca97a960f5de17d4928f0988e2946685d4f695a2059d5` |
| execution-a/jdk-oracle/verification.json | `1942de0a968d5baf77cb50ebd58bcb5592677e1c65ec31a00acbe1ea4074ed94` |

Root independently rebuilt the source/frame, exact owner and typed-prefix
machine proofs in `root-source-v183-a`, then reran the complete native,
tool-only JDK, eight-worker, ABI and pending/invalid-Context suite in
`root-execution-v183-a`. Both passed. The source receipt SHA256 is
`51e656c10e177e77b4c4a10596405c2f3bbf16879a87aa40739bf98c80271572`;
execution SHA256 is
`1a09b707e61ada620d757a28d6510eff8b346f3288710a1dac7fda0384bdc12d`.
All five actual-prefix mutation tests also passed. Root also checked all six
frozen code/test files before publication; this note was appended after review.
This repeats the standalone scope above; valid
Java Unsafe, DirectByteBuffer and combined bridge execution remain unverified.

## Subsequent bulk-read boundary

The original `ByteBuffer.get([B)` 52871 reaches `getArray` 52874. For large
reads it uses `ScopedMemoryAccess.copyMemory` 112724/Internal112725, original
`Unsafe.copyMemory` 113237 and native `copyMemory0` 113559 with descriptor
`(Ljava/lang/Object;JLjava/lang/Object;JJ)V`. That native is not part of the
42-entry typed module and is not implemented by this scalar slice.

An independent next slice must restrict the source to a null-base, live leased
RO owner range, and the destination to a validated normal heap byte array.
Original Java checks, signed sizes, source+length/destination+length overflow,
the actual array-base/byte-view ABI, and complete source/destination bounds must
be preserved. The read lock must cover the physical copy, with no Java callback
inside it. Writes into mappings, arbitrary off-heap copies and heap-to-heap
copies remain separate unsupported domains. The original source contract is
retained under `.boom/jimage-unsafe-read/source-inspection-a/bulk-copy-path.json`.
