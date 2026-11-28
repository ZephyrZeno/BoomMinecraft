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

## Current Consumer validation

The original Log4j `PropertiesUtil$Environment` Class, constant 90, binds
`Set.add(Object)boolean` as a `(Set)Consumer` factory. Its 649-byte derived Class
uses the already selected ordinary interface thunk, discards the boolean result
and retains the actual cast/invoke PCs 6/9. The 25-Class aggregate preserves the
original 24-Class source and machine prefix. Its ten runtime projections,
fifteen capacity consumers, complete 15-bank root geometry and entry count
changes pass separate physical checks. The complete 266-object image passes
independent whole-PE byte equality (`1ae457913ba10818e5e28d21c651f2e2c92c11bc18e5cd758e253569d313bff8`).

Four separate native component runs pass, reporting 39 basic, 2 pending-guard,
13 collection and 88 thread calls, 142 in total. Real original
`PropertiesPropertySource` constructors and `HashSet.size/contains` observers
verify fresh factories, duplicate-result discard and separate Sets. Wrong
argument types produce built-in Context kind 12 at SAM PC 6; null receivers
produce kind 4 at PC 9. Both retain method 530911. These built-in results do
not establish materialized Java exceptions or exact JDK messages. A separately
created real NPE remains byte-identical across both pending guards.

After workers stop and join, the collector uses all 15 root banks and one
additional closure root. Two collections retain the closure, Set, map,
PropertySource and Properties; removing the closure root lets all five be
reclaimed. Four real OS threads use normal Java Thread/FLS ownership, separate
Sets and sixteen fresh closures. All four runs pass the twelve cleanup checks
and unchanged-input checks. This establishes explicit quiescent collection and
thread isolation; automatic collection and game performance remain unverified.
Initial fixture metadata and error-number failures are retained separately.

Actual original Main then advances beyond constant 90 and stops at constant
110, `PropertySource.getPropertyNames()Collection` adapted to `Function`.
It exits 86 after 25.469 seconds without a timeout; cleanup flags are 7 and
held monitors and the registry lock are zero. The actual execution receipt is
`c249b9f3c5eaea0842b8bc11ae4808fe411dcfdc4563e048cedbbc95cf6efcf7`.
The new target needs an ordinary interface dispatch entry that is not already
selected. Its default method body does not justify bypassing receiver overrides.
Main Class initialization, Main execution, help output, the client and world
creation remain unfinished.
