# Instance method reference source APIs

`scripts/normal-lambda-instance-source.py` adds public, own-declared
`REF_invokeVirtual` (5) and `REF_invokeInterface` (9) implementations beside the
unchanged static rule (6). `site(sources, original_class, constant_index)` reads
the original bootstrap, method annotations, module exports and fixed loader
identities. `generated_class(contract)` returns Class bytes. Both functions use
the existing `normal-lambda-source.Sources` context; static contracts delegate
to the original implementation.

The rule supports bound and unbound receivers, reference captures and arguments,
reference result casts, exact primitive results, and discarding a result for a
void SAM. Each factory allocates a fresh normal object with ordinary reference
fields. Captures may be null. A receiver non-null check in the original caller
remains that caller's Java operation.

`scripts/normal-lambda-instance-assembly.py` exposes
`original_dispatch(contract, selection, available_symbols)`,
`body(generated_record, sources, binding)` and
`module(manifest, sources, dispatch_bindings)`. They render MASM source and
source-inverse facts. An instance target must have an already provided original
virtual/interface dispatch thunk matching its declaration, descriptor, receiver
constraint and table. Abstract declarations supply no body; native declarations
supply no new native implementation. Missing dispatch or native services remain
unsupported. Instance calls do not request static initialization of the declaring
owner. Frame PCs come from the actual generated Code, including compact loads
and five-byte `invokeinterface` instructions.

CallerSensitive and signature-polymorphic targets, special or constructor
handles, nonpublic targets, boxing, primitive argument adaptation, alternate
metafactories, serializable or bridge protocols, and unproved dynamic loader
access remain deferred. These libraries do not implicitly upgrade the existing
append API, its static rule verifier, or the protected runtime tool registry.
REF5/9 Classes require an explicit versioned semantics proof. Ordinary Object,
metafactory and SAM initialization dependencies, metadata capacities, Frames,
dispatch tables and all root banks remain separate integration requirements.

The published function and class ASTs are identical to the frozen source
implementations. Only their module descriptions and installed repository-root
resolution differ, with a complete source-byte inverse. A bounded replay
reproduces an existing static Class and the 649-byte interface-reference Class
exactly, including its argument cast at PC 6 and interface call at PC 9. The
interface Class also matches the original metafactory in a development JDK
oracle; this does not establish AOT typed-Throwable or exception-message
equivalence. Actual/canonical COFF checks and physical metadata checks belong
to separate machine receipts. These source APIs do not establish complete
MethodHandle support or Minecraft startup.
