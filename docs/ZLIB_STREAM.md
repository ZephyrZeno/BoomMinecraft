# Incremental zlib wrapper and Adler32 ASM candidate

This unregistered RFC1950 MASM slice wraps the frozen incremental raw-DEFLATE
kernel. It parses CMF/FLG incrementally, decodes the raw body, accumulates Adler32
only over actual output and checks the four-byte big-endian trailer. Input and
output buffers can change after every call. It does not replay input, change
the raw kernel or register an Inflater provider. JNI, dictionaries, gzip and CRC
remain unimplemented.

The primary specification is [IETF RFC1950](https://www.rfc-editor.org/rfc/rfc1950.txt).
Its20502 bytes are pinned in `.boom/zlib-stream/pinned-sources/rfc1950.txt` with
SHA256 `8f0475a5c984657bf26277f73df9456c9b97f175084f0c1748f1eb1f0b9b10b9`.
The RFC1951 and fixed JDK21 Inflater.c/Inflater.java pins from
[DEFLATE_STREAM.md](DEFLATE_STREAM.md) are also retained in the source contract.
JDK and Python are reference tools; the native image imports no decoder or OS
compression service.

## Exports and state

```text
uint32 boom_zlib_stream_reset(void* state, uint32 bytes);
uint32 boom_zlib_stream_step(Job96* job);
uint32 boom_adler32_update(AdlerJob32* job);
```

The wrapper state is34560 caller-owned bytes: a256-byte header followed by the
exact frozen34304-byte raw state. Call reset with34560 before using it. Reset
clears the wrapper and calls the original raw reset. Each state is opaque and
requires serialized access; distinct states can run concurrently. No allocation,
pointer to old input/output, mutable global or decoder import is retained.

| Wrapper offset | Field |
| ---: | --- |
| 0..19 | Magic, byte size, phase and sticky status |
| 20,24 | Parsed CMF and FLG |
| 28 | Adler32 of actual output, initialized to1 |
| 32 | Parsed DICTID, independent of output Adler |
| 36 | Declared window limit, `1 << (CINFO+8)` |
| 40,44 | Dictionary/trailer bytes acquired |
| 48 | Parsed trailer Adler |
| 52 | Remembered END_INPUT |
| 56,64 | Cumulative wrapper input/output |
| 256..34559 | Original raw state |

Phases0..7 are CMF, FLG, DICTID, raw body, Adler trailer, finished, error and
dictionary identified/unsupported. The wrapper reads raw private state only
through an explicit pinned dependency: kernel SHA256
`6be97c2d2305ce6cc9dc0deb3f2781214525dd6ac8560d3a3b19c67689bbb3bd`,
raw magic `0x315354464c464544`, size34304, phase offset12, bit-count32,
stored-remaining72, match-remaining100 and match-distance104. These offsets,
phase values, whole raw source, raw model and actual COFF are sealed. The
wrapper does not write raw private fields.

Job96 extends raw Job80:

| Offset | Type | Field |
| ---: | --- | --- |
| 0 | pointer | Initialized wrapper state |
| 8,16 | pointer,uint64 | Offered input and length |
| 24,32 | pointer,uint64 | Output and capacity |
| 40 | uint32 | Input flags, bit0=`END_INPUT` |
| 44 | uint32 | Status, also returned in EAX |
| 48,56 | uint64 | This call's bytes acquired/written |
| 64,72 | uint64 | Cumulative wrapper input/output |
| 80 | uint32 | Adler32 of actual output so far |
| 84 | uint32 | Parsed DICTID |
| 88 | uint32 | Trailer Adler acquired so far |
| 92 | uint32 | Output reserved, zero |

All nonempty buffers, the state and the job must be accessible and disjoint.
NULL empty buffers are allowed. Unknown flags, count/address overflow, overlaps
and input counts beyond `2^61-1` fail before decoding. Ordinary validation
failures publish3 or9 with zero per-call counts. NULL jobs and unsafe overlapping
or overflowing job/state layouts return3 without publishing into the job.
The valid separate state is preserved. Header checks do not authenticate
arbitrary caller edits to opaque parser data.

| Status | Meaning |
| ---: | --- |
| 0 | First zlib stream finished, trailer checked |
| 1 | Need input |
| 2 | Need output |
| 3 | Invalid arguments |
| 4 | Truncated after END_INPUT |
| 5..8 | Raw block, Huffman, symbol/repeat or distance error |
| 9 | Invalid wrapper state header |
| 10 | Invalid CMF/FLG |
| 11 | Trailer Adler mismatch |
| 12 | DICTID acquired; dictionary support is unavailable |
| 13 | Distance exceeds CINFO's declared window |
| 14 | Unexpected nested raw contract failure |

Input counts include actual header, compressed-body and trailer bytes acquired
in this call. Output counts include actual bytes written, even on errors.
Advance input only by `inputUsed`; resubmit any remainder. Old consumed input
and old output buffers may be released immediately. END_INPUT, empty calls,
output pauses and reset follow the raw streaming ownership contract. Finished,
decoding-error and unsupported-dictionary states remain terminal until reset
and consume/write zero on subsequent calls. Error progress is this decoder's
actual progress, not a claim to match zlib's error-time partial output.

## Header, body, dictionary and checksum

CM must be8, CINFO0..7 and `(CMF*256+FLG) mod31` must be zero. FLEVEL is accepted
for all four values and does not change decoding. Invalid CM/CINFO can fail
after the first acquired byte; invalid FCHECK fails after both bytes.

CINFO7 uses the full remaining output capacity for each normal raw call. For
smaller declared windows, the wrapper first advances raw decoding with zero
output to a pending stored/literal/match boundary. It then permits only that
operation's output span. A pending match distance is checked against the
declared window **before any byte of that match is copied**. This preserves the
raw kernel bytes and permits all valid small-window streams while rejecting
over-distance streams. It costs more calls than the usual32KiB path.

FDICT causes exactly four big-endian DICTID bytes to be read. Status12 then
leaves the compressed body unread, output count zero, output Adler1 and DICTID
in its separate field. No dictionary is accepted or pretended to be known.
Truncated DICTID returns4 only after END_INPUT. The pinned JDK reports DICTID
through `Inflater.getAdler()` while it needs a dictionary; a future JNI bridge
must select DICTID in that condition, rather than expose our output-Adler field
unconditionally. This slice provides no JNI bridge or setDictionary operation.

Raw final EOB leaves at most seven unused bits in its last acquired byte.
The wrapper validates that raw completion and reads its trailer from the next
input byte, without consuming another alignment byte. Trailer bytes can arrive
one at a time, including with zero output capacity. All four bytes are compared
with the checksum over actual output; mismatch consumes those four bytes then
returns sticky11. Complete trailing bytes and later zlib members remain unread.

AdlerJob32 is independent of stream state:

| Offset | Type | Field |
| ---: | --- | --- |
| 0 | uint32 | Packed input seed, normally1 |
| 4 | uint32 | Reserved input, must be zero |
| 8,16 | pointer,uint64 | Bytes and count |
| 24 | uint32 | Result |
| 28 | uint32 | Status0 or invalid-argument3, also EAX |

Update the next job's seed with the result. Both seed halves are reduced modulo
65521, including on empty input. Each5552-byte block is accumulated with
unsigned32-bit sums and then reduced. Starting from normalized sums, its maximum
s2 is4294690200, below `2^32`. Input is read-only, and pointer overflow,
NULL nonempty input and job/input aliasing are rejected.

## Deliberate compatibility boundaries

The frozen raw HDIST policy remains separate: RFC1951 declares1..32 distance
codes, while the pinned JDK and Python zlib reject counts above30 early. The
unused-reserved-code32-entry fixture is accepted by this raw kernel and rejected
by the JDK reference; decoded reserved codes still fail.

There is also an observed small-window policy difference. Seven complete
streams declare a window smaller than an actual match distance. This wrapper
rejects each with13 before copying that match. The local JDK accepts and
correctly decompresses all seven under all six fragment schedules:42 accepted,
zero rejected. These are an explicit policy group, with the JDK's entire
accepted output and consumed count verified. They are excluded from claims of
behavioral equivalence. The candidate is not complete Inflater compatibility.

## Actual verification and replay

With the primary pins present, from the repository root:

```powershell
D:\Dev\Python312\python.exe -B scripts/deflate-stream-candidate.py build --output .boom/deflate-stream/new-zlib-core
D:\Dev\Python312\python.exe -B scripts/zlib-stream-candidate.py build --raw-candidate .boom/deflate-stream/new-zlib-core/candidate.json --output .boom/zlib-stream/new-source
D:\Dev\Python312\python.exe -B scripts/zlib-stream-candidate.py verify --candidate .boom/zlib-stream/new-source/candidate.json
D:\Dev\Python312\python.exe -B scripts/test-zlib-stream.py --candidate .boom/zlib-stream/new-source/candidate.json --output .boom/zlib-stream/new-execution --thread-rounds 64
D:\Dev\Python312\python.exe -B -m unittest tests.zlib_stream -v
```

Every output directory must be new. Microsoft tools default to
`D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64`; JDK and Python are
build/reference tools. The wrapper object has exactly its three exports and
the two internal raw-function imports. LINK resolves those imports using the
original sealed raw COFF, with no library. The final DLL has no imports, entry
point, writable sections or decoder dependencies. Only the wrapper is newly
assembled; the original raw ASM/COFF remain byte-for-byte preserved.

Independent verification reruns the raw source/machine verifier, checks its
actual normalized COFF/image against the original raw receipt, reconstructs
the wrapper source and reassembles/relinks it. All nondebug wrapper COFF bytes,
symbols, relocations and unwind must match; the entire deterministic combined
PE must match too. The response file, source/private-layout pins, all objects,
tools and generated images are sealed and checked after execution. The wrapper
object is2829 bytes; the combined native DLL is7168 bytes.

Actual `.boom/zlib-stream/execution-b/execution.json` passed:

- 111 valid streams across6 fragment schedules, including0/1/2/7/512-sized
  input/output:666 stream runs and2205732 native steps. Python incremental zlib
  took2205741 reference calls and agreed on complete output and consumed bytes.
- All raw block/tree/match cases,32 CMF/FLEVEL combinations, and matches exactly
  at each of the eight declared window limits.
- 49 malformed header/raw/checksum cases,5 DICTID cases,7 explicit over-window
  policy cases and the separate HDIST32 case under all6 schedules.
- 3098 every-byte/specific-trailer split points,3083 truncated prefixes with
  943322 steps,98520 guard-page calls,20 reset/sticky/trailer protocol checks
  and22 validation calls. Guards include readonly input and output/state at
  either inaccessible page boundary.
- 55520 independent Adler whole/chunk calls, including custom seeds and empty
  input,all-0xFF data,5551/5552/5553-byte boundaries and100000-byte data;16
  further readonly guard-page Adler calls.
- Every normal call poisoned its old input/output buffers immediately.
  Eight distinct OS workers each ran64 small streams plus one history stream
  and one dictionary request:528 streams, with independent states/checksums.
- Test-only ASM ABI callers preserved8 nonvolatile GPRs,10 XMMs, stack pointer
  and two caller canaries across293251 step,173 reset and44 Adler calls, linking
  the exact original wrapper and raw COFF objects.
- 1038 JDK incremental reference cases with2671080 inflate calls and132
  independent Adler32 references. JDK DICTID/getAdler and the two policy groups
  are explicitly observed rather than silently treated as common compatibility.

Nine actual ML64/LINK negative cases reject changed Adler instructions, raw-call
relocation retargeting, unwind, private-helper export, PE headers, decoder
imports, extra RSP inputs, a redefined raw private layout and a substituted raw
object attempting to reuse the old receipt.

The first development run is retained in `source-a`/`execution-a`. It failed
because an empty Adler update returned a noncanonical seed unchanged. The
corrected kernel normalizes both halves for empty updates too. Its generated
source and new complete execution are in separate `source-b`/`execution-b`
directories; no old receipt was edited or promoted.

| Evidence | SHA256 |
| --- | --- |
| source-b/candidate.json | `b0b75e04fc3ed5cb508ff2093e0104b37e26c952b8b354f94d58e02c7966ebb9` |
| source-b/verification.json | `6efceb4e38430e141724cbe38f35bc82b2bb295b2767e4a8babc5cdd29d7f6dc` |
| execution-b/execution.json | `899c51b84535436d909ad6f95f400e09363086d9efd1409c53ea17a2c6e390af` |
| execution-b/ABI-probe/verification.json | `efa7f7d76aa9bfcbdfdece1676fc5bf27bb261de792a4ea2963d638f49755499` |
| execution-b/jdk-oracle/verification.json | `ccec7512dfb16017ef76af4f39980afa5251f0e50d60ec71d376d86137eadc24` |

The root reviewer independently rebuilt the wrapper against the separately
verified `root-source-v162-a` raw candidate and reran the complete suite in a
fresh process. `root-execution-v166-a/execution.json` is verified with SHA256
`ad60380c92688d0889125c9ccd61c9aa4ddcb7ee90a989e21e1c29aad271243f`;
`root-source-v166-a/verification.json` has SHA256
`d2bc2288969311d500e9db2e03536ab58fb1db7bbc52cccada002f553bf9d54d`.
The independent run repeated all 666 valid fragmented stream runs, 528 streams
on eight OS workers, guard pages, ABI checks and the complete JDK reference
suite above. All nine machine-proof mutation tests also passed. Both policy
differences remain explicit and no Java Inflater execution is claimed.

SetDictionary, dictionary validation/use, gzip/CRC, JNI fields/lifetime/exception
contracts, provider registration, Java Inflater execution and ZIP integration
are not part of this slice. No game/runtime acceptance is inferred from these
standalone native results.
