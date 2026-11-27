# Unsafe queries from normal Field objects

The assembly service implements the original internal Unsafe natives
`objectFieldOffset0(Field)`, `staticFieldOffset0(Field)` and
`staticFieldBase0(Field)`. The Java wrappers and the original native Frame32
rows remain intact. This is a query service over valid Fields in the original
metadata catalogue, not general reflection-based Field access.

The source model derives Field's packed `clazz`, class-local `slot` and
`modifiers` locations from the original Class/layout/UFMP data. The service
joins the declaring Class identity and slot to the exact immutable UFMP row.
It returns the existing opaque UFL2 token, consistent with name-based queries;
it does not expose a physical payload address. Static base is the canonical
declaring Class mirror. None of these queries initializes the represented
target class or creates a persistent root bank.

Normal Field copies retain the same query identity as their original roots.
The implemented domain validates these original catalogue identities and
modifiers. Fabricated slots or modified Fields are outside the tested domain;
the JDK native implementation does not define a checked Java exception
contract for those malformed inputs.

Null checks remain in the original `jdk.internal.misc.Unsafe` Java wrappers.
The separate `sun.misc.Unsafe` facade rejects record/hidden classes; those
restrictions are not added to internal Unsafe. Instance/static mismatches use
the original translated `IllegalArgumentException()` constructor and real
exception publication. Its null message matches the isolated Java21 oracle.

The reusable files are `native/providers/unsafe_reflected_fields.asm.inc`,
`native-config/unsafe-reflected-fields-abi.json` and
`scripts/unsafe-reflected-fields-source.py`. The source API consumes explicit
original summary, Class, selection, frame and layout inputs. It emits two MASM
units, with readonly UFRO128 metadata and no original Java Code changes.
Fresh CLI outputs stay under `.boom`, `target` or `dist`.

```text
python scripts/unsafe-reflected-fields-source.py --summary <summary.json> --classes <classes.jsonl> --selection <closure.json> --full-verification <selection-verification.json> --frame <frame-model.json> --layouts <layouts.jsonl> --output .boom/unsafe-reflected-fields-source
```

The first native component passed 14 cases and 83 original calls: native and
copied Field identities, exact UFMP tokens, agreement with name-based queries,
static Class bases, wrong-domain exceptions, public null exceptions, pending
Context preservation and no Random initialization. All 12 cleanup checks and
immutable input checks passed. It also exposed a diagnostic-origin defect:
successful exception construction left the last Java callback's PC/method.

A separate minimal revision saves the incoming PC/method/depth before that
callback and restores them after successful construction. It preserves a
constructor failure's actual error location. Four focused cases passed with
34 original calls and complete cleanup, without repeating the earlier suite.
Their SHA is `235d5d43abb34307fd6d68ad499bd54e57dcfe011eeee2fff01a4156e110c6b4`.
The restored values are the actual incoming Context, not an inferred caller.

Static offset/base queries do not establish general static Unsafe memory
access; the existing memory consumer's unsupported boundary remains explicit.
Automatic/concurrent collection and arbitrary generated-class Field queries
are also unverified.

The earlier 255-object Main experiment, using the first revision, progressed
to Striped64's primitive VarHandle call and completed resource cleanup. Its
Main class initialization and body still did not complete. This is not proof
of Minecraft, client-window or world startup.
