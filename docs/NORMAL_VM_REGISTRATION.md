# Normal-source VM registration and time adjustment

Batch schema 17 binds two original `jdk/internal/misc/VM` native declarations:
`initialize()V` and `getNanoTimeAdjustment(J)J`. Other declarations remain
unprovided. The normal source VM initializer and all its static fields stay Java
bytecode compiled by the own assembly backend; native registration does not set
the Java boot level or claim complete VM/System startup.

The contract follows [OpenJDK VM.c](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/native/libjava/VM.c):
the initialize native registers the performance-critical time-adjustment entry.
The supplied implementation is the existing MASM clock kernel, not JVM execution.
It reads Windows precise FILETIME, subtracts the Unix epoch and caller offset in
seconds, and returns nanoseconds only inside the strict interval
`-2^32 < seconds - offset < 2^32`. Out-of-range or overflowing offsets return -1.

## Runtime-owned target address

Pool32 retains the VMRG magic, state at 8, one target count at 12, target pointer
at 16, and reserved zero at 24. ABI 2 starts with a null target. Registration
atomically installs the actual clock implementation address from inside the
runtime DLL before publishing ready state 2. A caller's imported-function thunk
is never used as the implementation identity. Concurrent repeated registration
accepts the same target, rejects foreign targets and does not repair inconsistent
ready-without-target metadata. ABI 1 keeps its existing prelinked-target contract
for the older development compiler.

Both ABIs inspect the shared Context16/32 prefix and preserve pending errors. The
Context32 native adapters use a common generator, preserve original class-init
requirements and tail-call the MASM service. No Java boot field is written by the
native module. Independent checks reconstruct declarations, adapters, zeroed
pool data, actual COFF symbols and the kernel digest.

## Reusing executed source selection

`Invoke-DiagnosticStartup.ps1 -SeedDiagnosticDirectory <previous-run>` can seed
selection for a newly generated batch with the same locked input and IR identity.
The seed tool replays actual reached-Java admissions from the previous diagnostic,
checks recorded execution/source proofs, hashes class-result archives, and compares
class identity, method name, descriptor and original Code digest with the new
batch. Native, missing, failed and unverified methods cannot be seeded.

The seed records its execution provenance and adds zero native implementations.
It selects existing original Java assembly; every new round still uses a fresh
process/heap and independent source/COFF selection verification. Earlier seed
provenance is replayed recursively, with a bounded chain. Source/IR/root changes
reject the seed. This reduces repeated selection rounds; it does not synthesize
runtime semantics, reuse a live VM or certify a complete source closure.

## Development verification

`Test-BatchVmBootstrap.ps1` takes a completed, verified diagnostic VM-initializer
image. It checks cold source initialization, native target publication contention,
real clock calls, pending errors and malformed pools, and the ABI 1 path. The
existing 20,126-case arithmetic oracle and a JVM clock oracle remain development
tests. These tests do not establish System boot completion, Minecraft startup,
world creation, automatic memory reclamation or game optimization performance.

## v102 evidence

Both complete batches passed schema-17 source/COFF verification. Both original
VM initializers completed without diagnostic stops. Each side passed 8-worker
cold initialization, 8,192 fixture registration calls, 8,192 original-entry clock
calls, 12 rejected-metadata/pending-error cases, the legacy ABI 1 path, 20,126
deterministic arithmetic cases and 16 JVM clock comparisons. The registered target
was checked to lie inside the runtime DLL and the Java boot level stayed zero.

The seed control reused the v101 batch: four rounds became one, with the same
unprovided VM.initialize stop and zero native implementations added by selection.
On the newly bound v102 batches, both seeded System.initPhase1 diagnostics crossed
VM initialization and stopped at the unprovided `java/lang/Runtime.maxMemory()J`
declaration, method 42794. This is an actual frontier, not a completed phase.
