# Normal field reflection

`Class.getDeclaredFields0(boolean)` now has a normal-layout assembly candidate.
It enumerates original Class declarations and constructs a fresh `Field[]`
with the original translated `Field` constructor. The source projection covers
193,844 declarations, including instance fields, declaration slots, descriptors,
generic signatures and raw annotation attributes. It does not use the selected
static-state table as a substitute for complete Class fields.

The reusable source API is `scripts/normal-fields-source.py`; its runtime
fragment is `native/providers/normal_fields.asm.inc` and its ABI description is
`native-config/normal-fields-abi.json`. The explicit input models are the batch
summary, original classes, selected source, original frames and field layouts.
`index(...)` projects metadata; `render(...)` emits two MASM units. The source
tool runs during development/build preparation and is not a game runtime.

```text
python scripts/normal-fields-source.py --summary <summary.json> --classes <classes.jsonl> --selection <closure.json> --frame <frame-model.json> --layouts <layouts.jsonl> --source-verification <selection-verification.json> --output .boom/normal-fields-source
```

The CLI requires a fresh output under `.boom`, `target` or `dist` and checks
the summary, original Class and layout identities against the selected source.
It does not assemble, publish a provider or change Java source selection.

The native implements declared-field enumeration and public-only selection.
Original Java `Reflection.filterFields`, Field copying, roots and Class caches
continue through their translated methods. The service interns names, resolves
canonical type mirrors and preserves absent versus present signature/annotation
attributes. It does not initialize the class whose fields are queried.
Primitive and array Class queries return fresh empty Field arrays. Generated
classes outside the original metadata catalogue retain an explicit unsupported
boundary. The earlier VM-owned Field32 representation is a separate protocol.

Independent actual/canonical MASM and complete COFF checks cover both units.
An isolated component passed 12 cases and 972 original Java/native-frame calls:
Random's native 13/0 selection, repeated fresh arrays and Fields, interned names,
public Field copy/root/cache behavior, Field's native 13 versus publicly filtered
zero, empty Object/primitive/array cases, and ConcurrentSkipListMap's six
non-null generic signatures. Raw metadata and target initialization state were
checked separately. All 12 cleanup checks and immutable input checks passed.
Execution SHA is
`d24a3403720b924544a93555669d99c99f7bb838e69637491454f595d6dca0b1`.
The preliminary worker's gold-selection failure is retained as a separate
failed run; its correction changed the test harness only.

Nonempty runtime annotation bytes have source/machine coverage but were not
independently exercised by this AOT component. Annotation parsing, general
Field get/set operations and generated-class reflection are not established.

The 253-object original Main experiment passed complete independent PE
relinking and actual resource cleanup, advancing to the next missing native,
`Unsafe.objectFieldOffset0(Field)`. Main initialization and its body still did
not complete. This is not a Minecraft, client-window or world startup result.
