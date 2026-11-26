# Original Float/Double raw-bit native entries

Batch schema 19 supplies four original public static native declarations:
`Float.floatToRawIntBits(F)I`, `Float.intBitsToFloat(I)F`,
`Double.doubleToRawLongBits(D)J` and `Double.longBitsToDouble(J)D`.
Source class identity, finality, declaration flags and the absence of Java Code
are checked before generation and reconstructed by the independent verifier.
The ordinary Java canonicalization methods are not replaced by native stubs.

## Assembly contract

`native/runtime/java_bitcasts.asm` receives Context32, an argument-slot pointer,
BCST16 metadata and an operation. The own managed calling convention stores
floating values as raw integer slots and returns their representation in RAX.
Binary32 operations load a DWORD, clearing unrelated high bits; binary64 operations
load a QWORD. The service executes no floating-point instruction, allocation or
numeric conversion. It preserves signed zeros, subnormals, infinities and both
quiet/signaling NaN payloads. Pending errors survive without inspecting arguments.

BCST16 has magic `0x54534342`, ABI 1, operation count 4 and a reserved zero word.
Invalid metadata, operations or null argument pointers set raw error kind 7;
null contexts return without guest work. Source-bound adapters preserve original
Float/Double initialization requirements. Selecting the shared module includes
both source class states without premarking either initialized.

The contract follows the
[Float](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html)
and [Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
raw-bit APIs. The Java specification permits some platforms to quiet a signaling
NaN while returning/copying a floating value. This implementation avoids that
copy path by retaining the raw managed slot. The JVM development oracle records
any such observed signaling-NaN roundtrip variation separately. Non-signaling
patterns are compared exactly. The raw service never canonicalizes NaNs.

## Development verification

`Test-BatchBitcasts.ps1` uses an independently checked diagnostic image containing
the actual native module. A fresh heap/image executes the original Float/Double
initializers, checks their primitive TYPE mirrors, exercises the four native
entries and raw roundtrips, and checks pending errors and invalid metadata.
The sample includes binary32/binary64 boundary patterns and deterministic random
patterns; concurrent calls exercise shared immutable metadata. Canonical Java
wrappers are used only by the JVM oracle, not separately executed by this probe.

A separate kernel-only fixture checks the same raw data boundary without source
initialization and is explicitly marked as such. Neither fixture nor the native
probe proves full System boot, Minecraft startup, world creation, automatic memory
management or game performance improvements. Those remain actual-execution gates.

The v104 server and client native probes each passed 8-worker cold initialization,
8,236 binary32/binary64 patterns, 24,708 sequential native calls, 65,536 parallel
calls and 9 error checks. A separate kernel-only fixture passed 16,472 calls.
These counts describe the tested interfaces; they are not a percentage of game
completion. The canonicalizing Java wrappers are not included in this native
probe's executed scope.
