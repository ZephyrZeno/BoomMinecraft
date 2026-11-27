# Primitive VarHandle comparisons

The assembly bridge covers int/long instance-field `compareAndSet` and the
four weak-CAS modes: plain, default, acquire and release. It dispatches by the
original CP operation and actual VarHandle runtime family, then calls the
original translated static Java implementation. Those methods retain their
receiver casts and existing assembly Unsafe operations. No Striped64 field or
LongAdder value is special-cased by the runtime.

The enabled source policy contains 19 original CP sites, 32 selected Code
occurrences and ten operation/family target rows. Existing reference CAS
sources and their 46 sites are unchanged. The reusable files are:

- `native/providers/varhandle_primitive_cas.asm.inc`
- `native-config/varhandle-primitive-cas-abi.json`
- `scripts/varhandle-primitive-cas-source.py`

The source API rebuilds the original 36-family, 31-mode field directory from
explicit summary, Class, selected Code, diagnostic, layout and Frame models.
It does not consume a cached local directory as its implementation. Only the
verified int/long comparison rows are enabled; directory rows alone do not
establish runtime support. `index(...)` projects them and `render(...)` emits
the two MASM units. CLI outputs must be fresh ignored project paths.

```text
python scripts/varhandle-primitive-cas-source.py --summary <summary.json> --classes <classes.jsonl> --selection <closure.json> --diagnostic <diagnostic.json> --layouts <layouts.jsonl> --frame <frame-model.json> --source-verification <selection-verification.json> --output .boom/primitive-varhandle-source
```

The implemented nonexact shape has matching primitive coordinates, II or JJ,
and a boolean return. Widening, boxing and other conversions retain explicit
unsupported status20. Exact mode compares original coordinate types and uses
the original WrongMethodTypeException constructor for a mismatch; detailed
JDK error-message equivalence is not established. These adapters add native
unwind metadata, not invented Java stack frames or new oop-root banks.

An isolated component passed the original LongAdder constructor and add/sum
sequence, including a negative increment. The extended worker exercised
AtomicBoolean's five modes, normal and exact calls, typed errors, ten original
static Java delegates, pending Context preservation and eight real OS workers
with original Thread/FLS identities. Their 128 contended release-CAS attempts
over 16 rounds produced one winner per round and a real LongAdder sum of one.
All 12 cleanup checks and immutable input checks passed.

The basic execution SHA is
`e7594f3bbe979ec2af64e48c594cdb210dd906f17d0e68e393f7c62dd828b513`;
the extended SHA is
`c643e9f9e34f79f44881c1ae32511d5163d28a1fe387118b744275ebeacabcd8`.
Long weakPlain and weakAcquire have direct original-target evidence only:
there are no matching JJ-shaped CP sites in this source selection. The test
does not claim dynamic coverage of all 19 sites or every dispatch row.

The 257-object original Main passed full independent PE relinking, but its
actual run exited70 and failed strict cleanup verification. A read-only
hardware watch located the first unsupported operation in the pre-existing
field-only MethodHandleNatives resolver. The actual request is a static
`ServiceLoader.load(Class,ClassLoader)` method handle. This remaining method
domain and its cleanup failure are retained as failed evidence; the bridge's
component tests do not establish Minecraft or world startup. See
[the exact Main observations](NORMAL_LAMBDA_EXPANSION.md).
