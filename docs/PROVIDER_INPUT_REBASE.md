# Same-input provider rebase

`scripts/rebase-runtime-provider-inputs.py` is a development input producer. It
publishes a new **pending** provider set after a separately executed full batch
verification and current frame/provider verification. It does not accept a
provider set, run the game, or relax the direct-parent rule of
`extend-runtime-provider-set.py`.

The v149 operation rebuilds the same 65-slot JCLS data unit from the accepted28
64-slot parent with the current 105-tool namespace. Slot64 is the resolved,
mandatory, empty `jdk.jdwp.agent` module; slots0..63 and all Java units retain
their original identities and bytes. The accepted29 65-slot batch has a
historical 99-tool `runtime-provider-source.py` pin. Its old proof remains
historical: it is never copied to the new batch or passed off as current.

The producer requires an exact SHA256 for the original pending31 state and the
new full receipt. It checks the historical batch against that state's accepted29
checkpoint, independently enters the current named-module resolver for the new
batch, and requires the following before copying caches:

- The entire summary is equal apart from the JCLS assembly/object artifact
  records. All modules, packages, types, source profiles, layouts, Code hashes,
  and retained Java ASM/COFF records are therefore unchanged.
- Every full-verification field outside the named-derivation annotation is equal,
  including coverage and false execution claims. The old64 parent, resolved
  graph, module-info inputs, append declaration, and old64-to65 physical proof
  are equal.
- The historical provider source matches the old raw tool pin. Removing its
  literal `TOOL_FILES` assignment leaves exactly the same executable AST as the
  current source; the list changes only by the recorded six-entry 99-to105
  suffix. Other named-derivation source tool pins are unchanged.
- New and old65 JCLS ASM bytes match. COFF comparison covers nondebug procedure
  bytes, unwind data, relocation identities, per-index symbol semantics, physical
  module/root/loader tables, original writable data, and zero layout growth.
- All31 original provider manifest/receipt pairs and the frame receipt are
  pinned. Families, native IDs, exports, required-family closure, runtime DLL,
  and actual required kernel sources remain consistent.

`revalidate-runtime-provider-cache.py` then copies the original frame and all31
provider ASM/COFF/metadata files to fresh directories and runs the normal current
frame and provider verifiers. It does not invoke ML64. The producer checks all
copied byte digests, current tools, original inputs and current named lineage
again before publishing the new pending state. The runtime DLL remains the
original assembly runtime, SHA256
`572f28fac6ccf9851eca128929698c8d60c55d8b102972041f7f89a8dba05a26`.

Use a fresh `.boom/runtime-provider-rebases/` output directory. The CLI takes
`--state`, `--state-sha256`, `--batch`, `--batch-verification-sha256`,
`--old-provider-source` and `--output`. A historical source snapshot must match
the old receipt's full digest; an arbitrary source file cannot substitute for
that identity. This explicit producer currently permits exactly pending31 and
the recorded 99-to105 append, rather than inferring a generic tool migration.

Outputs include `source-equivalence.json`, a current independently verified frame
and 31 current verified provider copies, `reused-provider-bytes.json`,
`sealed-inputs.json`, `progress.json` and `pending-state.json`. Their scope keeps
`runtime_acceptance_complete`, `accepted_provider_set_published`,
`full_selection_reverified`, `game_started` and `world_created` false. A later
normal source selection and native execution must establish their own proofs.

The source boundary tests are in `tests/runtime_provider_input_rebase.py`.
The real v149 invocation and its outcome are recorded in the ignored run
directories, without modifying any original accepted or pending receipt.

The completed v149 run used
`.boom/named-module-batches/v149-jdwp-tool105-a`. Its real full verifier exited0
after350.391 seconds, producing summary SHA256
`9e9def42c1f36e6c2785d0e293935696a7d8ef117b23ea9d187fdeaf442517f0`
and full receipt SHA256
`c51c23008075341a2d7c738a8f690d88bed67a1a3d34697e9a9a6454971c5619`.
The separately executed rebase exited0 after339.734 seconds. Its new state is
`.boom/runtime-provider-rebases/io-park-tool105-v149-a/pending-state.json`, SHA256
`95f92cab38ecb4652c7905ea5b9ab5e167d261f8c5eb73d3bc8ed57835e66ad5`.
The current31 provider list is
`.boom/runtime-providers/io-park-tool105-v149-a/candidate/providers.json`;
the frame is `.boom/native-frame-overlays/io-park-tool105-v149-a/overlay.json`.

An independent ignored postcheck rehashed every sealed input and generated
provider manifest/receipt, compared every copied ASM/COFF/metadata file and the
frame bytes, and checked full coverage and pending-only scope again. Its report
is `.boom/provider-input-rebase-review-v149-a/verification.json`, SHA256
`a90488f2cda39637149e2ea6bf22e56f9895ce65f5b34a01bee275b6cdbf5630`.
It does not claim to rerun the provider models: those actual current models were
executed by the producer. Nine boundary unittest cases, Python compilation and
the targeted whitespace check passed.

To reproduce while this source namespace is current, use a fresh output name:

```powershell
D:/Dev/Python312/python.exe -B scripts/rebase-runtime-provider-inputs.py `
  --state .boom/formal-native-transitions/io-park-runtime-v149-a/pending-state.json `
  --state-sha256 66e428666bc53c9599265915616738829b6e9e025aa8822d9cfc8822677279cc `
  --batch .boom/named-module-batches/v149-jdwp-tool105-a `
  --batch-verification-sha256 c51c23008075341a2d7c738a8f690d88bed67a1a3d34697e9a9a6454971c5619 `
  --old-provider-source .boom/named-module-batches/v148-jdwp-production-a/producer-before-symbol-contract/runtime-provider-source.py `
  --output .boom/runtime-provider-rebases/io-park-tool105-v149-review
```

The original pending31 SHA256 remains
`66e428666bc53c9599265915616738829b6e9e025aa8822d9cfc8822677279cc`.
The new run preserves that original state, the old65 batch, accepted29 and all
previous receipts. Later tool changes require new evidence; these historical
hashes do not authorize editing a receipt or treating it as a new execution.
