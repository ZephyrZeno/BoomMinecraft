# Normal-source Unsafe bootstrap

The bulk compiler emits source-bound native adapters for four original
`jdk/internal/misc/Unsafe` declarations: `registerNatives`, `arrayBaseOffset0`,
`arrayIndexScale0`, and `fullFence`. Their flags and source identities must match
the locked Java 21 input before whole-input code generation begins. Other native
declarations remain unprovided. This module does not certify full Unsafe support
or Minecraft startup.

The game implementation is `native/runtime/java_unsafe.asm`. Rust generates
immutable tables and adapters; C# and the JVM are development test callers only.
There is no JVM fallback.

## Registration and source initialization

The source Unsafe initializer remains ordinary generated Java assembly. It calls
the supplied registration entry, creates the source-layout singleton, and fills
its own array constants through the original Java wrappers. Registration checks
the three prelinked native entries, including operation, method identity, entry
pointer, access flags and reserved storage, before publishing the pool ready with
an atomic compare/exchange. This is an explicitly partial AOT binding table.

`UnsafeConstants.<clinit>` also remains the original Java body. Its source static
cells begin at zero. An identified VM post-initializer fills the five cells only
after that body succeeds and before class readiness is published. It reports an
8-byte native pointer, the page size from `GetNativeSystemInfo`, little-endian
storage and unaligned scalar access on Windows x64. Cache writeback is disabled
and its capability size is zero. The hook does not initialize Unsafe or publish
the native table prematurely. This follows the injection order documented in
[OpenJDK UnsafeConstants](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/jdk/internal/misc/UnsafeConstants.java).

## Array and fence ABI

All instance calls validate a live source Unsafe receiver using the actual heap,
runtime type map and source object layout. Array Class arguments use the normal
canonical Class pool, never an opaque development mirror. The represented type
must be an array. Its element scale is derived from verified type metadata:
boolean/byte 1, short/char 2, int/float 4, long/double/reference 8. Normal array
payload starts at offset 0 from the managed pointer; object references are 8 bytes.
These implementation-specific values need not equal HotSpot's compressed-pointer
layout. `fullFence` executes `mfence`.

Pool80 (JUNS, ABI 1): magic/ABI at 0/4, state at 8, binding count at 12,
Class pool at 16, runtime type map at 24, heap cell at 32, source Unsafe layout at
40, Binding24 table at 48, scale table at 56, type capacity at 64, source Unsafe
class ID at 68, and five static-cell pointers at 72. Binding24 contains operation,
method ID, entry pointer, access flags and a reserved zero word.

Pending Context32 errors survive without guest work. Unregistered calls fail
with kind 20; null receivers/classes with kind 4; incompatible metadata or shapes
with kind 7. This does not yet implement normal Throwable materialization.

## Verification

Batch schema 16 adds an independently reconstructed source/assembly/COFF check.
The class-state verifier checks that the post-initializer follows the unmodified
source body. Selection includes the native object and both source class states;
diagnostic stop objects remain separate from semantic providers.

`Test-BatchUnsafeBootstrap.ps1` consumes an already verified diagnostic image and
tests source initializers, cold class-init contention, platform constants,
primitive and reference array layouts, the fence entry, repeated registration,
pending errors and rejected metadata. A JVM development oracle supplies platform
and primitive element-size comparisons. The probe is evidence for these paths,
not a complete linked vanilla image or an optimization benchmark.

Still required: object/static field offset resolution for normal inherited
layouts, typed memory operations and atomic updates, off-heap allocation/copy,
parking, dynamic class definition and other Unsafe services. The executed startup
diagnostic determines which family to implement next; unsupported calls must
never become successful zero-return stubs.

## v101 execution evidence

Both server and client batches passed independent schema-16 verification. Their
original Unsafe and UnsafeConstants initializers completed in fresh diagnostic
processes without reaching a stop. Each side then passed 8-worker cold source
initialization, 16,384 warm array/fence calls, 10 array Class cases, 20 original
static-value checks and 25 rejection/pending-error checks. Both initialization
orders were covered: Unsafe first in the diagnostic, Constants first in the
native execution probe. The JVM oracle checked platform constants and 8 primitive
array element sizes. Sixty-four of the 68 source Unsafe native declarations still
have no provider in this normal-layout module.

Ordinary Java assembly sources were unchanged from v99: all 877 server units and
951 client units have identical source digests. The newly working initialization
paths came from the shared runtime bindings and the explicit constants hook,
without rewriting the original Java methods. Whole-input Java generation was
nevertheless rerun in this checkpoint; cross-checkpoint object caching has not
been implemented or benchmarked here. These checks do not establish complete
System startup, game startup or game performance improvements.

v106 adds a separate [normal field lookup/address family](NORMAL_UNSAFE_FIELDS.md).
Its generated declarations and actual receiver maps reuse this bootstrap pool
without broadening the original three-row registration table. The normal-image
Unsafe coverage is now five of 68 native declarations in total. Typed memory,
reflection/static offsets, off-heap access and complete registration remain open.
