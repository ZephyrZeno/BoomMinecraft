# Normal-source Runtime memory and processor queries

Batch schema 18 binds the original `java/lang/Runtime` declarations for
`availableProcessors`, `freeMemory`, `totalMemory` and `maxMemory`. All four must
be public instance natives with their original descriptors. The original class,
private Java constructor and singleton initialization are preserved. `gc()` is
not supplied by this module and cannot become a successful empty return.

## Assembly execution boundary

The generated Context32 adapters ensure the source class, preserve pending errors
and call `boom_runtime_resource` in `native/runtime/runtime_resources.asm`.
RUNT64/1 contains the bound heap-cell pointer at 8, normal runtime type map at 16,
source Runtime type descriptor at 24, and zero policy/reserved storage at 32..63.
The service checks a live heap receiver and its actual type. Unsupported subtype
dispatch remains an explicit failure. No opaque development mirror is used.

Memory queries describe this runtime's fixed, committed arena, rather than a JVM
reference process. Total and maximum capacity are the heap capacity; free capacity
is that value minus occupied block spans, including allocation headers/alignment.
The occupied value is read once per query. Allocations and explicit quiescent
collection update the actual counters. This is consistent with the
[Runtime memory-query contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html),
which does not require different implementations to have equal heap sizes.
Automatic reclamation and Java stack/safepoint integration are not supplied here.

Processor queries execute the existing MASM Windows process/group/job-affinity
policy. They are resource observations, not evidence of Minecraft task scheduling
or game performance improvements. Java VM flag overrides are not accepted as
implicit policy for the assembly runtime.

## Verification boundary

The independent batch check reconstructs the original native declarations,
private constructor identity, zeroed policy data, exact assembly adapters and
actual COFF imports/exports. It hashes the resource, heap and type-map kernels.
Neither batch generation nor verification claims game startup.

`Test-BatchRuntimeResources.ps1` consumes a verified diagnostic image in which
the actual startup path selected these native adapters. In a fresh image/heap it
executes the original Runtime initializer/constructor, then tests the singleton
through its native resource entries. Allocation and explicit collection cases
are marked development fixtures. It checks counter changes, concurrent allocation
and queries, malformed inputs and pending errors. Processor results are compared
with disposable JVM oracle processes under affinity changes limited to the owned
test process, with restoration in `finally`.

The Java `getRuntime` getter is not separately called by the native probe; the
System startup diagnostic exercises its original source call path. Exact memory
byte totals are not compared with HotSpot. The shared-kernel change also passes
the existing legacy development-backend memory regression. Full System startup,
normal Throwable materialization, automatic memory management, game execution
and optimization benchmarks remain separate requirements.

## v103 execution evidence

Both schema-18 batches passed independent source/COFF verification. In both
fresh diagnostic images the probe executed the original Runtime initializer and
private constructor, then checked four native resource entries. Each side passed
8-worker cold initialization, 32,768 concurrent queries with fixture allocations,
three own-process affinity/JVM comparisons and 15 invalid-input/pending-error
checks. Thirty-two unrooted allocation fixtures were reclaimed at quiescence,
restoring the occupied-span/free-capacity relationship while retaining the source
singleton. Over-budget fixture allocation preserved counters. The prior compiler's
memory probe also passed against the v103 shared assembly runtime.

Both seeded System.initPhase1 diagnostics crossed the previously unprovided
Runtime.maxMemory entry in one round, then reached the unprovided original
`java/lang/Float.floatToRawIntBits(F)I` declaration (method 41900). This is the new
actual frontier. Complete System initialization and Minecraft startup are not
established by these results.
