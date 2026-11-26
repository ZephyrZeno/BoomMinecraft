# Incremental raw DEFLATE ASM candidate

This unregistered MASM kernel incrementally decodes one RFC1951 raw stream.
Caller-owned fixed memory holds the parser, Huffman trees and a32KiB history
ring. Input and output buffers may change after every call. No previous input
is replayed, and no complete compressed or decompressed stream is accumulated
inside the decoder. Stored/fixed/dynamic blocks and cross-block backward
matches have passed actual native execution with tiny buffers.

It leaves the frozen one-shot kernel, provider registry, shared tool namespace
and runtime unchanged. **It is not JNI Inflater compatibility or game startup
acceptance.** Wrappers, dictionaries, checksum handling and Java integration
remain separate work.

## Primary inputs

The normative input is [IETF RFC1951](https://www.rfc-editor.org/rfc/rfc1951.txt).
The source contract also pins fixed-tag
[Inflater.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libzip/Inflater.c)
and [Inflater.java](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/classes/java/util/zip/Inflater.java).
The first two files retain the pins in `.boom/deflate-raw/pinned-sources`:

| Input | SHA256 |
| --- | --- |
| rfc1951.txt | `5ebf4b5b7fe1c3a0c0ab9aa3ac8c0f3853a7dc484905e76e03b0b0f301350009` |
| Inflater.c | `b1e0fddcb21a0f99dcf80fdf500245b7bf76991445cb8b21a52787250e30ddae` |
| Inflater.java,31362 bytes | `ff3c671a1a8fab21d4258c2f73a88e77e84825b64df9a7c667f1966fd2a92b7d` |

`Inflater.java` was extracted unchanged from the locked local JDK21
`D:/Dev/Java/jdk-21/lib/src.zip` into
`.boom/deflate-stream/pinned-sources/Inflater.java`. The native bridge returns
31-bit input/output consumption and finished/dictionary bits; on data errors,
it publishes `inputConsumed` and `outputConsumed` before throwing. Java applies
these counts even when inflation throws. This motivates preserving accurate
progress on every return. Our ABI uses explicit64-bit fields and its own
continuation/error statuses. It does not implement that JNI packing, Java
fields, zlib buffer-refill policy or exception translation.

## ABI and ownership

There are two Windows x64 exports:

```text
uint32 boom_deflate_stream_reset(void* state, uint32 stateBytes);
uint32 boom_deflate_stream_step(Job80* job);
```

The caller provides exactly34304 writable state bytes and calls reset with
`stateBytes=34304`. Successful reset returns0 and clears the entire state,
including its history; invalid pointer/size/range returns3. Reset does not
allocate or free memory. Keep each state alive across calls and serialize calls
using that state. Distinct states may run concurrently. Treat state bytes as
opaque; arbitrary edits are outside the ABI. Its header, range and accounting
checks reject malformed headers but are not authentication for caller-written
Huffman tables.

Job80 has the following layout. RCX points to it and EAX returns its status:

| Offset | Type | Meaning |
| ---: | --- | --- |
| 0 | pointer | Initialized state |
| 8 | pointer | This call's input |
| 16 | uint64 | Input bytes available |
| 24 | pointer | This call's output |
| 32 | uint64 | Output capacity |
| 40 | uint32 | Input flags; bit0=`END_INPUT`, all other bits zero |
| 44 | uint32 | Returned status |
| 48 | uint64 | Input bytes acquired in this call |
| 56 | uint64 | Output bytes written in this call |
| 64 | uint64 | Cumulative input bytes acquired |
| 72 | uint64 | Cumulative output bytes written |

Buffers and the job must be accessible for their declared sizes, and must not
overlap each other or the state. Empty buffers may have NULL pointers. Pointer
addition overflow, unknown flags, input counts above `2^61-1`, cumulative count
overflow and overlapping nonempty ranges fail before decoding. A NULL job or
an overlapping/overflowing job/state layout returns3 through EAX without
publishing into that unsafe job. Other argument failures publish3 with zero
per-call counts; an invalid opaque-state header publishes9. Neither changes
the valid separate state. Cumulative fields on these validation failures are
zero rather than trusted state observations.

| Status | Meaning |
| ---: | --- |
| 0 | First raw stream finished |
| 1 | Need more input to resolve the current field/code |
| 2 | Need output capacity for a pending literal/stored byte/match |
| 3 | Invalid arguments/ranges |
| 4 | Truncated: more input was needed after declared end |
| 5 | Reserved block or invalid stored LEN/NLEN |
| 6 | Invalid Huffman tree/code, missing EOB or use of an empty distance tree |
| 7 | Reserved symbol or invalid repeat |
| 8 | Invalid backward distance |
| 9 | Invalid opaque-state header/accounting |

Advance the offered input pointer by `inputUsed`, append exactly `outputUsed`
bytes, then provide new buffers as needed. Unconsumed input must still be
provided; it is not implicitly retained. Input bytes counted as acquired are
copied into the bit cache or already decoded, so their old buffer can be
released. Written output is immediately copied into the internal history ring,
so old output buffers can also be released. Error progress describes this
implementation's actual reads/writes, not zlib's partial-output policy.

`END_INPUT` means the supplied chunk reaches the end of available stream input.
If output fills before the whole offered chunk is consumed, resubmit its
remainder with the same end declaration. Once the entire marked chunk is
acquired, EOF stays in the state across output-full returns. An unfinished
state then rejects attempts to append new input; if it eventually needs another
byte, it returns sticky truncated4. Without an end declaration, exhausted input
returns1 instead. This API intentionally distinguishes incomplete input from a
caller who knows it is truncated. Finished and decoding-error states remain
terminal, consume/write zero on later calls and require reset for reuse.

A zero-capacity call can still consume headers or a code and preserve a pending
literal/match before returning2. At a stored payload or pending output, output
capacity takes priority. At a header or undecoded code, input availability takes
priority. Empty calls are allowed; they do not fabricate progress. The caller
must eventually supply the resource requested by status1 or2.

## Fixed parser state

The header stores only scalar values, never input/output/state pointers:

| Offset | State fields |
| ---: | --- |
| 0..23 | Magic, byte size, phase, sticky error, BFINAL |
| 24..39 | Bit buffer and bit count |
| 40..63 | Cumulative input/output and logical consumed-bit position |
| 64..75 | History position/count and remaining stored payload |
| 76..95 | HLIT/HDIST/HCLEN, current index and previous code length |
| 96..107 | Pending symbol, remaining match and match distance |
| 108..127 | Partial Huffman code/first/index/length/table identity |
| 128..139 | Extra-bit base/width and remembered EOF |
| 256..895 | Literal/length canonical table |
| 896..1023 | Distance canonical table |
| 1024..1151 | Code-length canonical table |
| 1152..1471 | Temporary code lengths |
| 1472..1503 | Code-length alphabet lengths |
| 1536..34303 |32768-byte history ring |

Phases0..16 are header, stored alignment, LEN, NLEN, stored copy, dynamic counts,
code-length alphabet, decoded lengths, repeat extra bits, compressed symbol,
pending literal, length extra bits, distance symbol, distance extra bits,
pending match, finished and error. Complete parser fields are read atomically;
at most23 cached bits are retained when a field needs more input. A partial
Huffman prefix has its own scalar state. Each literal, stored byte and match
byte updates the ring immediately. Match copying resumes at its remaining
length and reads the ring with forward-overlap semantics.

The bit reader only acquires bytes needed for the current field/code. At final
EOB, cumulative input is exactly `ceil(logicalBitPosition/8)`; unused bits in the
last byte are permitted and complete trailing bytes are not read. Stored
alignment consumes only its padding bits. The same tree validity and reserved
symbol rules as the one-shot kernel apply. The explicitly separate RFC HDIST
1..32 versus zlib/JDK count<=30 policy remains documented in
[DEFLATE_RAW.md](DEFLATE_RAW.md); it is not counted as Inflater compatibility.

## Build, verification and actual execution

With the three primary files above present, from the repository root:

```powershell
D:\Dev\Python312\python.exe -B scripts/deflate-raw-candidate.py build --output .boom/deflate-raw/new-stream-reference
D:\Dev\Python312\python.exe -B scripts/deflate-stream-candidate.py build --output .boom/deflate-stream/new-source
D:\Dev\Python312\python.exe -B scripts/deflate-stream-candidate.py verify --candidate .boom/deflate-stream/new-source/candidate.json
D:\Dev\Python312\python.exe -B scripts/test-deflate-stream.py --candidate .boom/deflate-stream/new-source/candidate.json --one-shot-candidate .boom/deflate-raw/new-stream-reference/candidate.json --output .boom/deflate-stream/new-execution --thread-rounds 64 --fuzz-cases 2000
D:\Dev\Python312\python.exe -B -m unittest tests.deflate_stream -v
```

Output directories must be new. Microsoft ML64/LINK defaults are under
`D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64`; Python and JDK are
build/reference tools. The DLL has exactly the two native exports, no entry
point, no imports, no writable sections and no mutable globals. The producer
seals source, primary pins, helper/parser source, tools and all generated
ASM/COFF/RSP/PE. Independent reassembly compares all nondebug COFF sections,
symbols, relocation targets and unwind. Independent deterministic linking must
match the entire PE, including headers and padding. Post-run hashes protect
the original artifacts. The output COFF is4396 bytes and the DLL5632 bytes.

Actual `.boom/deflate-stream/execution-b/execution.json` passed:

- 71 complete streams across6 fragment schedules: `(in1,out1)`, `(2,7)`, `(7,2)`,
  `(512,512)` and two mixed schedules including0-sized buffers. This is426
  successful stream runs and1733811 native steps, with the same final output
  and consumed byte count as Python's incremental zlib and the ASM one-shot
  reference.
- All stored/fixed/dynamic cases from the one-shot corpus, maximum15-bit data
  codes and7-bit code-length codes, all length/distance codes, plus stored→fixed
  history across multiple ring wraps and fixed→dynamic32768-byte matches.
- 1452 every-byte split points for small compressed streams, including empty
  partitions;120124 observed partial-Huffman suspensions. All resumable parser
  phases were observed:0 and2..14. Alignment phase1
  completes from the already acquired header byte.
- 22 malformed streams under all6 schedules,1295437 truncated-prefix steps
  with sticky EOF errors,70424 guard-page calls,22 reset/sticky/EOF protocol
  checks and26 validation calls. Guards cover readonly input and output/state
  against inaccessible pages at either boundary.
- Every normal call immediately poisoned its old input and output buffers.
  A suspended match with32768 valid history bytes was copied as34304 opaque
  bytes to a new address. Resuming at1/1 versus mixed chunk sizes produced
  identical output and completely identical final state bytes.
- 2000 deterministic random fragmented inputs:7 complete streams matching
  zlib and1993 rejected inputs;5155 bounded native steps.
- Eight distinct OS workers, each with64 small streams plus one cross-block
  history stream:520 streams in total with separate states on the same DLL.
- A separate test-only ASM caller preserved8 nonvolatile GPRs,10 nonvolatile
  XMMs, stack pointer and two caller canaries across226258 step and95 reset
  invocations of the original kernel COFF.
- 564 JDK incremental reference cases and1993901 actual inflate calls checked
  output SHA256, finished/reject outcome, per-call counters, cumulative
  bytes-read/written and remaining input. Python and JDK are references only.

Eight actual ML64/LINK mutation tests reject changed step instructions,
relocation targets, unwind, private symbol promotion, PE headers, added imports,
extra RSP arguments and altered state/history ABI claims even after artifact
hashes are refreshed.

| Evidence | SHA256 |
| --- | --- |
| source-b/candidate.json | `1317bf388642ba9cd000af4b47749befa91d1611e9018b0deddbd6105a03da31` |
| source-b/verification.json | `0158e6a4d6963a8dec85ca9d5f16211f453f4e9fe180d7019331031b2631a9bc` |
| execution-b/execution.json | `ffd264dffa5dbc3e8528e3edfd8764f023548bee0974ff3df6603c7cb3f14c61` |
| execution-b/ABI-probe/verification.json | `32897791bc4949e82615d86e1356b6eeeafd0e59d317d492dba6cabd873491cd` |
| execution-b/jdk-oracle/verification.json | `252bdde95c9f373ed0e894425128e2465cb076b84b8ec7c76656ea45e5a68071` |

This slice does not support zlib/gzip wrappers, dictionaries, Adler/CRC,
JNI/native-provider registration, Java Inflater fields/lifetime/exceptions or
ZIP integration. A malformed/truncated stream is terminal until reset; it is
not repaired by later input. Finite differential tests are evidence for the
stated scope, not a proof of complete Inflater behavior.

The root independently rebuilt the DLL and repeated the complete64-round,
2000-fuzz suite, including all426 stream/schedule runs,1733811 ordinary steps,
guard pages, state relocation, eight OS workers, ABI probes and564 JDK cases.
All eight machine mutation checks also passed. Fresh proof
`.boom/deflate-stream/root-source-v162-a/verification.json` has SHA256
`5268704a05176bf75509d4a4f9312cf3a3e07cfe4caa163c1a7289fe0450766f`;
`.boom/deflate-stream/root-execution-v162-a/execution.json` has SHA256
`b4183775862a22eaff70003e75d3dca1c6e6c121873116279ca7274569fe3187`.
No JNI or wrapper compatibility is added by this replay.
