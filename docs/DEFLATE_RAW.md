# One-shot raw DEFLATE ASM candidate

This unregistered development kernel decodes one complete RFC1951 raw stream in
MASM. Stored, fixed-Huffman and dynamic-Huffman blocks, overlapping matches and
32KiB backward distances have passed actual native execution. It has no decoder
imports, allocator or mutable global data. It does not change the runtime DLL,
provider registry, current tool namespace, original Java or previous receipts.
**This is not an Inflater implementation or complete Minecraft acceptance.**

The normative input is [IETF RFC1951](https://www.rfc-editor.org/rfc/rfc1951.txt).
The bridge reference is fixed-tag
[OpenJDK21.0.13+3 Inflater.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libzip/Inflater.c).
The latter calls zlib in the reference JDK; neither it nor zlib is linked into
the delivered ASM kernel. Local primary inputs are under
`.boom/deflate-raw/pinned-sources`:

| Input | Bytes | SHA256 |
| --- | ---: | --- |
| rfc1951.txt | 36944 | `5ebf4b5b7fe1c3a0c0ab9aa3ac8c0f3853a7dc484905e76e03b0b0f301350009` |
| Inflater.c | 10247 | `b1e0fddcb21a0f99dcf80fdf500245b7bf76991445cb8b21a52787250e30ddae` |

## Native contract

`boom_deflate_raw64(Job64*)` uses the Windows x64 ABI. RCX points to the
64-byte writable job below; EAX returns the same status written at offset52.
The caller provides accessible buffers for the declared ranges. The job,
nonempty input and nonempty output ranges must be disjoint. Integer overflow,
NULL nonempty ranges, input lengths above `2^61-1`, and overlapping ranges
return status1 before decoding. A NULL job returns1 without writing it.
Zero-length input and output may have NULL pointers. Valid disjoint input is
read-only; output fields in a non-NULL job are reset before range validation.

| Offset | Type | Meaning |
| ---: | --- | --- |
| 0 | pointer | Input bytes |
| 8 | uint64 | Input byte count |
| 16 | pointer | Output bytes |
| 24 | uint64 | Output capacity |
| 32 | uint64 | Bytes containing consumed bits, `ceil(bitPosition/8)` |
| 40 | uint64 | Bytes written |
| 48 | uint32 | Bits consumed in the last byte, `bitPosition mod 8`; 0 at a byte boundary |
| 52 | uint32 | Status |
| 56 | uint64 | Exact input bit position |

| Status | Meaning |
| ---: | --- |
| 0 | Complete first raw stream decoded |
| 1 | Invalid arguments/ranges |
| 2 | Truncated input |
| 3 | Insufficient output capacity |
| 4 | Reserved block type or invalid stored LEN/NLEN |
| 5 | Invalid Huffman tree/code, missing EOB, or use of an empty distance tree |
| 6 | Reserved literal/distance symbol or invalid code-length repeat |
| 7 | Back distance exceeds produced output or 32768 |

The bit reader performs no lookahead. A successful call stops at the final
block's EOB (or stored payload end), allows unused padding in the final byte
and leaves all trailing complete bytes unread. Concatenated raw streams stop
after the first stream. On errors, counters describe this implementation's
actual reader/writer progress. A decoded literal can consume its symbol before
discovering output-full; a match validates its entire destination span before
writing it. A stored block validates its entire payload and destination span
before copying. This does not promise zlib's error-time partial output policy
or a resumable state.

Canonical trees reject oversubscription. Code-length trees must be complete;
literal/distance trees only allow the one-bit single-symbol incomplete case.
An all-zero distance tree is allowed until a match tries to use it. EOB256 is
mandatory. Repeat16 cannot be the first length; repeats16/17/18 may span the
literal/distance boundary but cannot exceed the combined length count. Fixed
trees include the specified reserved entries; decoding286/287 or30/31 fails.
Stored blocks align to the next byte and require the exact LEN/NLEN complement.
Every match copies forward byte by byte, including distance-one overlaps.

One RFC-vs-zlib policy difference is deliberately separate: RFC1951 section3.2.7
declares HDIST in the range1..32, and distance30/31 must never occur in the
compressed data. This kernel accepts a declared32-entry tree whose reserved
entries are never decoded. The pinned JDK and Python zlib reject a declared
count above30 early. The separate fixture records both results; it is excluded
from common compatibility claims. Reserved codes actually decoded are errors
in both fixed and dynamic trees.

The decoder saves all Windows nonvolatile registers and uses less than2KiB of
native stack including its private helper calls. Each call owns its tables and
workspace. No shared decoder state or external dictionary is read.

## Verification and replay

From the repository root, with the pinned primary files already present:

```powershell
D:\Dev\Python312\python.exe -B scripts/deflate-raw-candidate.py build --output .boom/deflate-raw/new-source
D:\Dev\Python312\python.exe -B scripts/deflate-raw-candidate.py verify --candidate .boom/deflate-raw/new-source/candidate.json
D:\Dev\Python312\python.exe -B scripts/test-deflate-raw.py --candidate .boom/deflate-raw/new-source/candidate.json --output .boom/deflate-raw/new-execution --fuzz-cases 10000 --thread-rounds 256
D:\Dev\Python312\python.exe -B -m unittest tests.deflate_raw -v
```

Every output directory must be new. The default Microsoft tools are under
`D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64`; the reference JDK is
`D:/Dev/Java/jdk-21`. These are build/reference tools. The kernel DLL does not
use a JVM, Python, Windows compression APIs or any other decoder.

The producer seals primary pins, ASM, producer/COFF-reader source, assembler,
linker, exact response file, COFF and PE. Independent verification reconstructs
the source and recompiles it in a fresh directory. It compares all nondebug
COFF bytes/flags, symbol identities, relocation targets and pdata/xdata. With
`/BREPRO`, the independently linked PE must match the **entire** original image,
including its headers and padding. The PE must have one direct executable
export, no imports/delay imports/CLR, no entry point and no writable section.
Output/input hashes are checked again after verification/execution.

`tests/deflate_raw.py` has10 actual ML64/LINK mutation cases. With refreshed
artifact digests it still rejects changed instructions, readonly tables,
relocation targets, unwind data, private-to-public promotion, PE headers,
PE code, imports, added RSP arguments and false ABI metadata.

Actual native run `.boom/deflate-raw/execution-c/execution.json` passed:

- 69 complete streams, including all three block types, mixed unaligned blocks,
  sync-flush blocks, arbitrary final padding, empty and single distance trees,
  15-bit data trees, a7-bit code-length tree, all29 length/all30 distance codes,
  overlapping copies and an exact32768-byte back distance.
- 22 malformed fixtures,1559 truncated prefixes,222 guard-page calls (readonly
  input ending at an inaccessible page and output at either guard boundary),
  184 output-full calls and11 argument/NULL/overflow/alias checks.
- 10000 deterministic random inputs (47 complete,9953 rejected) and552
  single-bit mutations of valid streams (379 complete,173 rejected), with
  output and exact consumed-byte checks against Python zlib.
- Eight distinct OS workers,256 calls each, using the same native DLL with
  independent jobs and workspaces.
- A test-only ASM caller preserved all8 nonvolatile GPRs, all10 nonvolatile
  XMM registers, stack pointer and two caller canaries across91 success/error
  calls of the exact original kernel COFF.
- 92 JDK reference cases checked output SHA256, finished/error outcome,
  bytes-read/bytes-written and remaining bytes. This includes the separate
  declared-HDIST32 policy rejection and both decoded reserved-distance errors.

Evidence hashes:

| Artifact | SHA256 |
| --- | --- |
| source-c/candidate.json | `c6696279eeeb8763e102f570a2c1565c57a8c1187adf07e4296bce32a90586ca` |
| source-c/verification.json | `f151ccff31e18311b07d7f6e086fab3c4b0a4721e110444a52cd45d55d7e98cb` |
| execution-c/execution.json | `4411143c3d450fac31727d826c916fd63df8164ebd740821dd37a4981afd0980` |
| execution-c/ABI-probe/verification.json | `1c6438ac946c2c407530a94d6191241dd525f96f3ff49bdcb5bd539f7ef51793` |
| execution-c/jdk-oracle/verification.json | `1ff059b6964548713807133e2f6efea5bbde47c4dcb09c34c87f622b5d7d4be9` |

Incremental input/output, a persistent/resumable stream, zlib/gzip wrappers,
Adler/CRC validation, preset dictionaries, JNI field/lifetime/exception
contracts, ZIP integration and original Java Inflater execution remain undone.
Output-full is an error on this one-shot ABI, not an Inflater continuation.

The root independently rebuilt the candidate and repeated the complete suite,
including10000 random inputs, eight workers with256 iterations, guard pages,
the Windows ABI probe and92 JDK cases. All10 machine mutation checks also
passed. Fresh proof `.boom/deflate-raw/root-source-v159-a/verification.json`
has SHA256 `9312d6f1366f6e1bc5c64e31fd1c381ede8c55540f1cdc1a80ef3b811f15fa39`;
`.boom/deflate-raw/root-execution-v159-a/execution.json` has SHA256
`534f26ac7d93540072984d9587af2164f8433362ec94c194eae4f7be8b12479e`.
The same one-shot and unregistered boundaries apply.
