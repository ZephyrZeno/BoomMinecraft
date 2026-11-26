# JCLS named module append candidate

The candidate evidence below records the producer at commit `b87ed8e`. The
current schema-2 producer also supports a separate real `verify-full` pass and
strict production closure lineage. Historical receipts retain their original
source hashes; they are not receipts for the updated producer. Current commands
and verification are recorded in the production section below.

`scripts/refresh-named-module-batch.py` derives one JCLS data unit from the
verified v145 bootstrap-unnamed batch. This is a development data candidate;
it does not produce `verification.json`, claim full source verification, or run
the game. The current production verifier intentionally rejects its new module
domain. The parent batch, all original Java units, native frame object, runtime
DLL, and provider directories remain immutable.

## Why the missing module is required

The locked snapshot
`.boom/jdk-modules/d769a9c293a743028ce21c126d19a685/jdk-modules.json`
uses `jdk21-system-classpath-default`. Its default root `jdk.jdi` has a mandatory
`requires jdk.jdwp.agent` edge with flags `0`, verified directly against the
original `jdk.jdi/module-info.class`. The resolved graph includes
`jdk.jdwp.agent` with the application defining loader. Its descriptor has no
packages or classes, so the original JCLS construction from represented types
did not create its identity.

The script reads the actual original classfiles and checks the call chain:

1. `ModuleBootstrap.boot2` (113710) calls `ModuleLayer.defineModules` after
   constructing the boot configuration.
2. `ModuleLayer.<init>` (42318) calls `Module.defineModules`.
3. `Module.defineModules` (42279) constructs normal named `Module` objects for
   the configuration.
4. The normal constructor (42233) calls the original `defineModule0` native.

This establishes the requirement for the locked default bootstrap path. It
does not claim that the current native execution has reached the missing
module. No debugger, account, or JVM fallback is involved.

## Exact data change

The candidate appends `{id: 64, name: "jdk.jdwp.agent", loader: 2}`. All prior
module IDs remain stable, including application unnamed 44 and bootstrap
unnamed 63. The source type index and all 109,803 provided type rows remain
unchanged. Type capacity remains 109,945; three loader keys remain unchanged.

Only four complete declarations change in the original ASM bytes:

- The JCLS module count becomes 65.
- The contiguous normal root count becomes 110,013, increased by one.
- The module-loader table gains one `DWORD 2`.
- The module root array gains one QWORD.

The resulting source is exactly nine bytes longer. Existing Class, loader and
module root positions stay stable; the reverse table and following BSS symbols
move by eight bytes. The new root joins the same normal contiguous GC bank.
The loader table alignment moves the immutable Class records by eight bytes;
their data and relocations relative to the record base remain identical.
The script creates no Java objects or class initialization states.

## Physical proof and limits

The script uses the verified parent resolver and pins the parent summary, full
receipt, source plan/classes, input state, original frame artifacts, runtime
DLL/metadata, assembler, and its helper sources. It requires exactly the
missing resolved named modules, a mandatory path from a default root, original
descriptor hashes, empty packages, and no original classes belonging to an
appended module. It rejects an existing or duplicate requested module.

The new data unit is assembled with the original `ml64.exe`. Verification
reconstructs the four byte edits and entire derived summary, checks actual COFF
section inventory/flags and export/import sets, and compares:

- All instruction sections and every instruction/unwind relocation byte.
- All writable pool data except the independently checked module count.
- The original Class/name bytes and record relocations, normalized only for
  their moved record base.
- The physical root count, full module-loader table, contiguous Class/loader/
  module root span, reverse table and following BSS size.
- Writable-data relocations and assembler CodeView records; only the actual
  object filename may differ in CodeView.

The 1,011 original Java unit records are retained without compilation. This
uses the real parent full receipt and original immutable records; it does not
relabel that parent receipt as a new full verification.

The first successful candidate is
`.boom/named-module-batches/v147-jdwp-append-b`:

| Artifact | SHA256 |
| --- | --- |
| `summary.json` | `9742a838d55ceb233f42c6a7745640b3e747fda9022d659aaebbc02025a4f4d6` |
| `named-module-derivation.json` | `e3b32a06eced98790d16ec55ae6c0d746b7bee134a86f9b49a69a2852484b0b8` |
| `jcls-candidate-verification.json` | `3bef8fd111f64215cb8213fddb2194982884e5d57379195a2f4cbfccfbea2d8a` |
| `class-literals/0000.asm` | `ee8390ec0527f9062fe229b139d599662fbec79237283a940eec86ddb27f8bbd` |
| `class-literals/0000.obj` | `4096ede3340b51de696fe0c9dd728ef03a37894bcc7fc1fb9444630595a3589d` |

The proof covers 151,381 original instruction bytes, 16,819 code relocations,
219,606 original data-record relocations and exactly eight extra BSS bytes.
An independent new Python process reran the candidate verifier successfully.

Ten negative cases passed in
`.boom/named-module-negative-checks/95110004443b4111bdac0af2db099a31/result.json`
(SHA256 `53c50ff5c956564b10e3121b6461db79e3a8d7a9cd39175bd1aa8c712a65fbb4`).
They include real COFF mutations of an instruction, a code relocation, module
count, GC root count, appended loader key and original type record; duplicate
and already-existing module requests; the real production Class verifier's
module-domain rejection; and the ordinary fixed-root resolver's inability to
inherit this new candidate's parent artifacts. No old evidence was overwritten.
The initial `-a` attempt failed at its final input seal because that comparison
mixed two-field frame digests with three-field full digests. Its source snapshot,
failed status and generated files remain in place; the corrected tool used the
fresh `-b` directory.

The primary agent independently rebuilt this candidate in
`.boom/named-module-batches/root-review-v147-a` and invoked the verifier in a
separate process. The actual source/COFF check passed with slot 64, 1,011
original Java units retained, and no full-batch or runtime acceptance claim.
The original 0..63 slots remain unchanged.

## Historical production blockers

These were the three blockers at the historical `b87ed8e` candidate stage. The
two validator changes are implemented by the current production integration;
the Boot native still requires normal regeneration for the enlarged pool.

1. `verify-batch-classes.identities` currently reconstructs modules only from
   represented types plus the explicit bootstrap unnamed slot. The real verifier
   rejects 65-slot metadata with `Normal Class layout/loader/module source
   differs`. A future narrow extension must independently validate the appended
   names/loaders against the locked resolved module snapshot, retain every old
   key, and reconstruct the enlarged normal root bank and ASM.
2. `closure-batch-artifacts.py` does not recognize
   `named-module-derivation.json`. Future integration needs a strict parent-chain
   resolver that permits only certified retained artifacts plus this JCLS unit,
   with a new genuine full receipt. This candidate deliberately supplies no
   production resolver override.
3. The original `normal-boot-unnamed-module-v1` package binds a precise module
   count. Its actual sealed COFF compares `[rdi+88]` to 64 and branches on
   inequality. The new physical JCLS header is 65. Its metadata also seals the
   module/root counts. This single native package must be regenerated and
   reverified with the exact 65-slot model; its guard must remain exact.

The actual old-COFF guard/new-header observation is sealed in
`.boom/named-module-script-check/boot-native-exact-capacity-blocker.json`
(SHA256 `984908f02d671c2866ab5e3eab47ab5bd3c074f458703cf3f0d7b83f863224d2`).
It is a read-only instruction/header observation, not a new execution receipt.
No shared verifier, generator, registry, runtime or provider source was modified
for this candidate.

The independent Module5 model has read the candidate in
`.boom/module-definitions/source-model-65-a.json`: 65 slots, 63 named modules,
772 packages, two edge words, and no missing names. Its second word accommodates
named slot 64; synthetic unnamed identities start at 128. This is a source-model
check over an unverified candidate batch, not component or game acceptance.

## Historical reproduction (`b87ed8e`)

Use the `b87ed8e` source version and a new output directory for every historical
candidate build. The current producer requires an accepted input state instead:

```powershell
python -B scripts/refresh-named-module-batch.py build `
  --state .boom/formal-native-transitions/windows-runtime-v147-a/pending-state.json `
  --module jdk.jdwp.agent `
  --parent-summary-sha256 83a311219b3af267757be5eda15bce2094a2d38e50ccca6de3e5f3bc0f74a2f3 `
  --parent-verification-sha256 b1abda904b5f3109b9c59e83ff49d23726fc97a553bf96167c91cacfe40485ef `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/named-module-batches/independent-review

python -B scripts/refresh-named-module-batch.py verify `
  --output .boom/named-module-batches/independent-review
```

The current helper-source hashes are part of the candidate seal. Preserve the
producer source version when later production integration changes those helpers;
do not rewrite old receipts to make them match a new source namespace.

## Current production verification

The schema-2 producer now accepts a scoped accepted input state. `build` still
proves only the data append. `verify-full` separately invokes the real complete
`verify-batch-assembly.verify` with the original source IR and a narrowly bound
artifact resolver. It recalculates all original source, method, metadata and
COFF checks. The entire parent receipt must match, field for field, including
all false execution claims; only the new named-module lineage is added. The
original checked bootstrap lineage annotation is retained. Inputs and producer
hashes are reconstructed again after the expensive pass, before atomic receipt
publication.

`verify-batch-classes.py` independently reconstructs the original module prefix
from source types. It derives the extra no-type names and loaders from the
locked resolved graph and actual module-info descriptors. It does not use a
candidate acceptance flag to choose names, loaders or old slot positions. Its
existing full canonical ASM and Class/type/COFF verification then runs over
the enlarged pool.

`closure-batch-artifacts.py` recognizes only the strict named-module lineage
with a genuine full receipt. Its resolver allows original parent artifact
records except the replaced JCLS pair, plus exactly the new JCLS ASM/object
inside the child `class-literals` directory. Wrong roots, unlisted records,
changed digests, wrong module directories and the removed old JCLS pair are
rejected. The original VM image home survives the closure wrapper, preserving
the original normal properties profile.

An additional real COFF attack was found during this integration: swapping
undefined `boom_t0`/`boom_t1` at indices 21/22 preserved the old symbol set and
raw relocation indices while redirecting their actual targets. The isolated
fresh-ml64 reproduction is
`.boom/named-module-symbol-review/76604fa0f0674040abb535e4226aa140/result.json`
(SHA256 `abb5d4a40e539d5aa3527cfbb589eee5c5297d850822d190c3db9a581396bf55`).
The updated proof checks every symbol index's name, section, storage, type,
auxiliaries and value. Values may move only by the precisely checked immutable
record/BSS shifts; section auxiliary sizes must match their actual headers.
The unchanged complete string table is also checked. This binds unchanged
relocation bytes to unchanged semantic targets.

The first production `-a` complete verifier naturally passed in 310.688 seconds
before this extra symbol check. Its receipts remain historical and its nine
producer/helper sources are saved under
`v148-jdwp-production-a/producer-before-symbol-contract/`. It is not used as a
receipt for the strengthened producer.

The final batch is `.boom/named-module-batches/v148-jdwp-production-b`. Fresh
ml64, the actual complete verifier in a new process, and a separate production
closure resolver process all passed. The full pass naturally exited 0 in
308.766 seconds. The symbol contract covers 228,061 table entries / 228,056
records, with only an eight-byte immutable-record shift and eight-byte BSS
shift. All 1,011 original Java units and prior IDs remain unchanged.

| Final artifact | SHA256 |
| --- | --- |
| `summary.json` | `271870db974403d34343f7218a781e118caeef3bf79c3b18188df992a3f17056` |
| `named-module-derivation.json` | `a200f1b0ad220348043a17ec19768a6f78414af7f3c98e0ecdf0035b7baa4381` |
| `verification.json` | `9252005a2e8b02422d5beb4dc8aee15c2cf0c9e9eb0dabc8538f29b0f12f1cff` |
| `source-closure-lineage-verification.json` | `88cb18736469cf0cdefe762bb25e6147a2db06ca7306d73b1bc8e099981aaee7` |

The independent production closure proof confirms 2,487 summary artifact
records are exactly the retained parent set minus the old JCLS pair plus the
new pair. Five negative resolver cases passed. Seventeen tests across
`tests/named_module_batch.py` and `tests/closure_batch_artifacts.py` passed,
including false module/loader, moved old slot, unrelated COFF replacement,
actual code/relocation/symbol-target mutation, physical root/loader counts,
complete parent-receipt coverage and ordinary schema compatibility. The final
log is `.boom/named-module-production-checks/unit-tests-final.log`.

This verifies the complete unlinked source batch and its closure lineage.
It does not certify native runtime execution or accept a new provider set.
`normal-boot-unnamed-module-v1` still must be normally regenerated with its exact
65-slot guard before use with this batch. Runtime572, all original Java code,
the input frame and every old artifact directory were preserved.

Current reproduction uses a new directory and the accepted 28-family state:

```powershell
python -B scripts/refresh-named-module-batch.py build `
  --state .boom/accepted-native-windows-runtime-v147-28.json `
  --module jdk.jdwp.agent `
  --parent-summary-sha256 83a311219b3af267757be5eda15bce2094a2d38e50ccca6de3e5f3bc0f74a2f3 `
  --parent-verification-sha256 b1abda904b5f3109b9c59e83ff49d23726fc97a553bf96167c91cacfe40485ef `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/named-module-batches/production-independent-review

python -B scripts/refresh-named-module-batch.py verify-full `
  --output .boom/named-module-batches/production-independent-review `
  --ir .boom/translation-ir/server-v85-2a52b09a09944122baae25b0ddbd4e99
```
