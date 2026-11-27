# MethodHandle field resolution

The native field resolver, native-binding publication service and ordered field
lookup are assembly implementations. The Python source tool projects original
Class, Code, field-layout and frame metadata into five MASM units; it is a
development/build tool and is not part of the executing game runtime.

The reusable sources are:

- `native/providers/method_handle_bindings.asm.inc`
- `native/providers/method_handle_field_resolve.asm.inc`
- `native/providers/source_field_lookup.asm.inc`
- `native-config/method-handle-field-abi.json`
- `scripts/method-handle-field-source.py`

The source API takes explicit batch-summary, original classes, selected source,
original native frames and layouts. It derives Java IDs, callbacks, descriptors,
packed field offsets, Record status and ordered field-search data from those
inputs. It does not read local test coordinators or depend on a particular
generated epoch. Outputs must be fresh paths under `.boom`, `target` or `dist`.

```text
python scripts/method-handle-field-source.py --batch-summary <summary.json> --classes <classes.jsonl> --selection <closure.json> --frames <frame-model.json> --layouts <layouts.jsonl> --source-verification <selection-verification.json> --output .boom/method-handle-field-source
```

`project(...)` returns the source model and readonly lookup payload;
`render(model, payload)` returns the five assembly sources. Projection alone
does not assemble, register a provider, execute Java or verify a game image.
The tool remains separate from the frozen 117-tool provider identity.

Registration validates original native declarations and frames before
publishing all 13 bindings under an assembly SRW lock. The registrar adds a
fourteenth native wrapper. Original `invoke`/`invokeExact` frame flags96 are
preserved; bit64 is not reinterpreted as CallerSensitive. Published bindings do
not imply that unsupported MethodHandle operations have implementations.

Field resolution uses original declaration order, recursively ordered direct
interfaces and then the superclass. It returns canonical declaring Class and
flags, preserves the original `resolution` field for Java Factory to finish,
and does not initialize the represented target class. Offset operations return
the VM's opaque field token rather than a raw payload address. VM-info results
use ordinary translated Java allocation and callbacks. No new oop root bank is
introduced by these services.

The bounded implemented domain is Class-typed field MemberNames. Unsupported
method/descriptor forms and caller-loader constraints remain explicit; this
is not a complete MethodHandle invocation runtime. Error tests separately
check real typed exceptions, message text and unchanged original object fields.
The source API also rejects cycles in the provided field-search hierarchy.

Validation includes 17 pure lookup cases, native publication and concurrent
publication cases, direct field-handler checks and 13 distinct error-path
cases. Original Java execution covers the cold native registrar, Factory,
Lookup and ConcurrentSkipListMap initialization/construction. The reusable
emitter reconstructs all five executed source units byte for byte; actual and
canonical MASM outputs match their complete verified COFF contributions.

The independently relinked 249-object integration checkpoint uses these services and
advances to a VarHandle signature-polymorphic call. It still exits86 before
Main initialization completes. Neither complete Minecraft startup nor client,
world, general MethodHandle support or game performance is established. See
[the actual Main observations](NORMAL_LAMBDA_EXPANSION.md).
