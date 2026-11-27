# Assembly owner for a real readonly JIMAGE mapping

This unregistered Windows x64 slice opens and holds real JIMAGE file mappings.
It supplies the resource ownership needed by a future VM bootstrap and native
Java buffer bridge. It does not implement `NativeImageBuffer.getNativeMap`,
Java class initialization, library loading, resource decoding or game startup.

The fixed OpenJDK21 sources distinguish
[native map lookup](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjimage/NativeImageBuffer.cpp)
from [opening a reader](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjimage/imageFile.cpp).
`getNativeMap` only finds an existing reader. This new owner must therefore be
opened explicitly by the real resource bootstrap before a bridge can expose a
hit. An absent mapping remains a miss; it is not manufactured by returning an
arbitrary address or skipping the original Java initializer.

The owner uses `CreateFileW`, `CreateFileMappingW` and `MapViewOfFile` with real
readonly handles and views. Its handle shares reading only. It checks the
28-byte header, little-endian magic, version1.0 and the complete index bound
`28 + 8*table_length + locations_size + strings_size <= actual_file_size`.
Flags and resource count are not given invented restrictions. Big-endian input
is explicitly unsupported. Optional expected size is checked against the actual
file. This is a header/range contract, not complete resource validation or a
cryptographic input check; input preparation must pin the original image.

Keys are exact UTF16 code units, without case folding or path normalization.
For supported paths this preserves the original modified-UTF8 key equality.
Embedded NUL is explicitly rejected. The owner copies exactly the supplied
units and adds its own Windows terminator; it does not read beyond that span.

The caller owns an aligned, initially zero 128-byte pool and accessible,
disjoint job/key memory. Its native exports are:

```text
uint32 boom_jimage_owner_init(Owner128*, uint32 bytes, uint32 capacity);
uint32 boom_jimage_owner_open(Job64*);
uint32 boom_jimage_owner_lookup(Job64*);
uint32 boom_jimage_owner_release(Job64*);
uint32 boom_jimage_owner_close(Owner128*);
```

Job offsets are pool0, UTF16 path8, unit count16, token24, view32, file bytes40,
status48 DWORD, Win32 error52 DWORD and expected file size56. Release receives
only pool/token; lookup requires expected size0. Return EAX equals job status.
Pool magic is `0x3130474D494A4F42`, bytes128, ABI1; state at24 is ready1,
closed2 or draining3. All pointer/count fields are 64-bit unless stated.

Every successful open or lookup takes one lease. Repeated exact opens reuse
the real mapping, while generations survive close/reinitialization so old
tokens cannot release a new entry. Release drops a lease and keeps the cache.
Close refuses active leases. A Java bridge must retain each successful buffer's
lease until its Java and native users have ended; successful construction alone
is not permission to release or unmap it.

Status0 succeeds;1 is lookup miss;2 busy;3 invalid arguments;4 OS failure with
actual Win32 error;5 invalid pool;6 unknown/unleased token;7 capacity/generation
exhaustion;8 embedded NUL;9 closed;10 image/header/expected-size failure;11
unsupported endian;12 incomplete OS cleanup. Cleanup checks every actual
unmap, handle close and allocation release. Failure retains the unfinished node
and its real resource counts in state3. Only release and close can then drain
or retry it; no new view is returned. Closed pools may be explicitly initialized
again. Init and raw caller-owned structures require exclusive caller ownership.

The implementation contains no mutable global data, Java oops, decoder, CRT or
JDK calls. It imports 11 explicit Windows APIs. Java wrapper ownership and a
controlled VM shutdown still need integration.

Actual source-b verification independently reassembles all nondebug bytes,
section flags, full symbols/auxiliary records, relocation targets and unwind,
and reproduces the complete DLL. Receipt SHA256 is
`6ec3754a85349d6d261bf53184fd4fa6fce4142ae3834e4d99a911cbfd13883e`.
The independently executed final suite is
`.boom/jimage-owner/execution-i/execution.json`, SHA256
`4026f969acf78617bc42fe7f5410b8a8c3cd36f7fa533981b050778c4ee835a9`:

- The real locked141325186-byte JDK image maps to its complete original SHA256.
  Eight OS threads perform1024 shared leased reads, concurrent duplicate opens
  and busy closes. Exact misses, stale tokens, capacity and size checks pass.
- Six invalid/unsupported header cases, readonly sharing and an exact UTF16
  input ending at an inaccessible page boundary pass.128 further complete
  mapping lifecycles leave Windows handle count unchanged.
- The development driver releases its Python executor/thread objects and
  prepares its reference file IO before the handle baseline. Earlier failed
  measurements remain in execution-a through execution-g; they are not native
  success receipts. The final run has159 handles before and after.

The separate protocol suite retains the exact production object for139 Win64
calls, checking eight nonvolatile GPRs, ten XMM registers, stack and two canaries.
Ten controlled Win32 failure cases verify failed-open rollback, retained
unmap/map-handle/file-handle/allocation failures, safe retries and release of an
existing lease while an orphan drains. Its observer changes only whitelisted
test import names; all nondebug instructions, sections, aux and relocations are
compared. Production source/COFF are not changed. Its receipt SHA256 is
`ae0ed5915454b1963d462e2897d9200e75f358bdf6adaa82306d692128c587f2`.
Nine actual COFF/PE/response/scope mutation tests also pass.

With fixed native source pins present at the paths recorded by the builder:

```powershell
D:/Dev/Python312/python.exe -B scripts/jimage-owner-candidate.py build --output .boom/jimage-owner/new-source
D:/Dev/Python312/python.exe -B scripts/test-jimage-owner.py --candidate .boom/jimage-owner/new-source/candidate.json --output .boom/jimage-owner/new-execution
D:/Dev/Python312/python.exe -B scripts/test-jimage-owner-protocols.py --candidate .boom/jimage-owner/new-source/candidate.json --output .boom/jimage-owner/new-protocols
D:/Dev/Python312/python.exe -B -m unittest tests.jimage_owner -v
```
