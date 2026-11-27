# Readonly JIMAGE to normal heap byte-array copying

This unregistered slice implements the original `Unsafe.copyMemory0` declaration
only for a null source base whose complete range belongs to a live leased
[JIMAGE owner](JIMAGE_OWNER.md) record, and a destination that is a real byte
array allocated by the original ASM heap. It neither permits arbitrary
off-heap copying nor changes the 107-tool namespace, existing runtime DLL,
production 42-entry typed memory module, Java Code, or frozen
[scalar read slice](JIMAGE_UNSAFE_READ.md).

## Original consumer and native contract

The source model discovers the private native declaration from the original
Unsafe class: `copyMemory0(Object,long,Object,long,long):void`, access0x102 and
native frame flags32. Its current method ID is113559; this number is an example
from the locked inputs, not the lookup key used by the implementation.

The original `ByteBuffer.get(byte[])` 52871 reaches `getArray` 52874. Large reads
use `ScopedMemoryAccess.copyMemory` 112724/Internal112725, then the original
`Unsafe.copyMemory` 113237. That method calls `copyMemoryChecks` 113239 atpc9,
returns atpc19 for zero bytes, and calls the native atpc29 otherwise. The model
hashes the whole original methods and checks that order. Those Java checks,
session handling, source/destination array checks, and zero-byte return are not
rewritten. The new native is outside the existing 42 typed declarations.

Native argv remains six QWORD slots:

| Offset | Value |
| --- | --- |
| 0 | normal Unsafe receiver |
| 8 | source base, supported only when null |
| 16 | actual source mapping address |
| 24 | destination normal heap byte array |
| 32 | original Unsafe destination byte offset |
| 40 | signed byte count |

The model verifies the current original byte-array allocation kind8, physical
tag264, zero reference prefix, scale1 and array-base offset0 against the locked
bootstrap/array/typed-view sources and runtime metadata. The service subtracts
that verified base before passing a payload offset to the core. It does not
assume HotSpot's array-header offset.

`native.obj` supplies the ordinary Frame8 adapter and original method aliases,
plus the new native service. The adapter retains normal class initialization,
trace entry/leave and Context handling. The service validates the actual UFMP
and Unsafe receiver using the original typed receiver prefix before accessing
the normal heap. The prefix has a larger fixed, unwindable native stack frame;
the original runtime service is untouched.

The new domain excludes heap-to-heap, nonnull source base, null/off-heap
destination, reference/Boolean/other primitive arrays, and mapping writes.
Unsupported domains explicitly fail with Context20; malformed private protocol
arguments use Context7. The implementation does not claim JDK equivalence for
invalid private native pointers. A pending Context preserves all32 bytes.

## Copy kernel and lifetime

`boom_jimage_owned_copy_to_bytes(Job64*)` receives owner0, normal heap8,
source address16, destination byte-array oop24, destination payload offset32,
byte count40, status48 DWORD, reserved52 DWORD and copied56 QWORD.

Status0 copies;1 rejects an unleased/unowned source range;2 rejects sizes,
offsets or bounds;3 rejects owner metadata;4 rejects a nonready owner;5 rejects
a non-byte-array destination;6 rejects a destination outside the actual heap.
The caller supplies accessible native structures whose lifetime covers the
call. A usable job publishes status and zero copied bytes on rejection. Invalid
or overlapping job/owner structures do not publish output fields.

The kernel calls the unchanged ASM `boom_heap_contains` before inspecting the
destination header. It checks physical byte-array type, zero reference slots,
signed sizes/offsets, destination payload bounds, and all address additions for
overflow. It then holds the actual Owner128 shared SRW lock while validating a
ready record, positive lease, exact source range and physical `rep movsb`.
Source address+length and record view+length are both checked for overflow.
Every locked failure releases the lock. No callback, allocation or managed
collection occurs inside that interval. Mapping close/release requires the
exclusive lock. Collection remains explicitly quiescent and the owner/heap
allocations outlive all users.

The core allocates no global mutable state and retains no Java oop after the
call. The source-native bridge consumes the actual JMAP80/1 pool with Owner128
at8 and ready state at24. Its candidate/proof/source are sealed as dependencies;
no host-written owner cell or fake Java metadata is used.

## Actual verified scope

Source-a's independent verifier reconstructs the original native and Java
contracts from locked class bytes, validates current full batch/Frame8 and
unchanged runtime kernels, checks the frozen owner/bridge inputs, independently
reassembles all nondebug native/core instructions, data, symbols, relocations
and unwind, and reproduces the complete linked copy/owner PE and exact RSP.

`.boom/jimage-unsafe-copy/execution-b/execution.json` is verified, SHA256
`a3521ad47074cfae3717c0784203e66401311192875ac01a0644d30a6de4207f`:

- 3127 actual copy calls include532 reference cases of zero, tiny, unaligned,
  large and final-byte ranges. Complete destination bytes, including unchanged
  bytes outside the requested slice, match Python and a tool-only JDK mapped
  ByteBuffer.get oracle. Job inputs and surrounding native canaries stay intact.
- 532 calls through a test-only ASM observer use the exact production core
  object and preserve8 nonvolatile GPRs,10 XMM registers, stack and two canaries.
- Eleven rejection cases cover missing/partial/wrapping source ranges,
  negative sizes/offsets, destination bounds, Boolean/reference arrays,
  off-heap destinations and attempted writes into a readonly mapping. Rejection
  leaves copied0 and the normal destination unchanged.
- Eight distinct OS threads each complete256 copies into independent normal
  heap arrays. Quiescent GC frees10 objects; the rooted byte array then remains
  usable with the same native mapping.
- A real32MiB copy exposes the held shared lifetime lease while an exclusive
  release/close runs. Copy output is complete and exact. Both owner pools finish
  in state2 with entries, leases, mapped bytes and native handles all zero.
- 23 pending/invalid protocol calls use the exact service/receiver source with
  the unexecuted adapter removed only in this test-only fragment. Actual cold
  bridge data is linked without publishing an owner. All eight pending Context
  DWORDs are unchanged. This negative protocol fixture does not claim a valid
  Java Unsafe receiver or an executed normal Frame8 adapter.

The first execution-a remains failed and retains its original harness snapshot.
It reached the core, concurrency, GC and large-copy checks, then failed while
assembling the negative protocol fixture because its now-local cold bridge
definition still had an EXTERN declaration. Execution-b removes that one test
declaration. No native algorithm, candidate object or old receipt was changed.

Five coherent actual-COFF mutation tests reject a weakened destination type,
a length guard testing the wrong register, retargeted heap membership,
retargeted shared-lock release and changed normal native-adapter unwind. Their
new object hashes are recorded before invoking the canonical machine verifier;
the rejection is not merely a stale artifact hash check.

Normal Java Unsafe receiver execution, the complete Frame8 adapter at runtime,
original ByteBuffer.getArray execution and the combined bridge runtime remain
unverified by this standalone suite. They require NIO's independently verified
normal source selection and actual combined overlay. The current evidence has
`registered=false`, `bridge_runtime_binding_verified=false`,
`full_selection_reverified=false`, and `game_started=false`.

## Reproduction

Keep first failures and use fresh output directories:

```powershell
D:\Dev\Python312\python.exe -B scripts/jimage-unsafe-copy-candidate.py build --state .boom/formal-native-transitions/manifest107-31-v157-a/pending-state.json --owner .boom/jimage-owner/source-b/candidate.json --bridge .boom/jimage-native-map/source-bound-v176-c/candidate.json --output .boom/jimage-unsafe-copy/review-source-a
D:\Dev\Python312\python.exe -B scripts/test-jimage-unsafe-copy.py --candidate .boom/jimage-unsafe-copy/review-source-a/candidate.json --output .boom/jimage-unsafe-copy/review-execution-a
D:\Dev\Python312\python.exe -B -m unittest tests.jimage_unsafe_copy -v
```

| Evidence | SHA256 |
| --- | --- |
| source-a/candidate.json | `3af59640ed24a0811c970dbc341415ca33edc97980565de943596dcdc26e3d47` |
| source-a/verification.json | `4a910cbf8c837013f8724f871a30c2af50a631aab57f669307c87b79a3580080` |
| execution-b/ABI-probe/verification.json | `739e78ee582cb10fad2c2fe33d616567f0871431be86592742dab67ef36e075e` |
| execution-b/jdk-oracle/verification.json | `4a3169b4d4433a8f64c9132e1630167bda1c00863311624b6aa385c98e9a941c` |
| execution-b/source-protocol/verification.json | `e6c8216ae3d62ad203eed6c2431362cb9e72841e205a19b4ec5fb75eb57bff3f` |

Independent review rebuilt the source, original native frame, complete COFF and
PE in `root-source-v186-a`; its verification SHA256 is
`2f669f21cd3a393c608d38bb16ca8d1ff2e5f68aaf8533e2a63e1e87afb6ffd1`.
The fresh `root-execution-v186-a/execution.json` has SHA256
`d2e5f866d19a78bf810d7adb86769ccfc84af4020cc95ec08bf2bc85fa9290e2`.
All 3,127 copy calls, 532 reference and production ABI cases, eight OS workers,
pending-context checks, quiescent collection and the 32 MiB copy passed again.
The five actual machine mutation tests also passed independently. This retains
the standalone scope above: the original Java bulk consumer and complete
normal native adapter have not been executed by these receipts.
