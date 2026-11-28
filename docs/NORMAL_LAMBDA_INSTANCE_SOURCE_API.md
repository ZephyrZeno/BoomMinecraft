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

## Generating a missing interface dispatcher

`compiler::batch_dispatch::project_generated_interface` accepts a complete
original `Catalog`, its normal layouts, an explicit generated-call request and
the provided Java/native method sets. It reuses the existing declaration
resolution, method selection and target-record algorithms. It enumerates every
original receiver with a normal layout before checking target availability.
Unselected receivers are retained, and missing Java or native bodies remain
visible in the returned target records. The caller must separately validate
the actual generated Class/Code and its original access, module, loader and
ordinary-target annotation contract.

`render_generated_interface` reuses the existing table and site renderers with
compiler-owned names, leaving all original numeric table IDs unchanged. The
output contains a readonly DSPV1 table, receiver constraints and a native leaf
thunk that jumps to the existing `boom_batch_virtual_invoke`. It allocates no
Class IDs, defines no new dispatch kernel or object roots, and performs no
declaring-Class initialization.

For the current `PropertySource.getPropertyNames` reference, actual Rust
projection over the locked original IR selects all four original receivers:
52010 calls 510711, 52038 and its subclass 52043 call 510839, and 52060 calls
511069. All three override bodies are already provided. The resolved default
declaration 510899 is not substituted for these runtime choices. Independent
selection and complete source reconstruction agree with the Rust output.
Actual/canonical COFF and physical checks cover all 120 readonly bytes, seven
ADDR64 relocations, the entire 19-byte thunk, three REL32 relocations and its
empty native unwind record. Two existing dispatch tests also pass.

The source libraries, generated caller, runtime metadata and dispatcher retain
separate acceptance scopes. A caller compiled with an unresolved dispatcher
keeps that pending dependency in its receipt; complete image composition must
prove the new dispatcher's unique actual definition. The appended Rust API
also has an exact immutable snapshot/inverse for every original source byte.
The new dispatcher has not yet been accepted by an original Main run.

## Unbound Function reference oracle

A development JDK compares the original CP110 metafactory with the actual
540-byte generated hidden Class in the same lookup, module and loader domain.
Nine functional cases per implementation, plus three direct reference
observations, pass in both default and `-Xint` modes; the two complete stdout
streams are identical. Original Properties/PropertySource constructors use two
controlled property names. Return contents, override selection, null-input
behavior and wrong-type exceptions, including their messages, agree. A direct
default-interface call produces an empty Collection and remains a separate
observation. No environment or unrelated game data is enumerated.

Factory identity is recorded separately: the original metafactory reuses its
noncapturing instance in this test, while the generated factory allocates a
fresh instance. The [Java 21 LambdaMetafactory contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html)
permits either a new or a suitable existing function object and does not
guarantee identity-sensitive results across implementations. This permitted
choice is not reported as byte-identical factory behavior. Direct MethodHandle
null-call messages are also preserved separately from hidden-function messages.
These JDK observations do not establish AOT typed-exception/message fidelity or
Minecraft startup.

## Actual Function execution and the next Main stop

The 267-object current26 image passes an independent whole-PE comparison,
receipt SHA256 `74427c3fadc139630e8bb331d15dc7c181768e88a77770cf9d7f97b5246f40d9`.
Its isolated Function component passes 32 basic, 2 pending-setup and 112 thread
report entries, 146 in total, plus two explicit pending-guard calls. Original
Properties and PropertiesPropertySource constructors populate controlled keys;
the original Function interface thunk reaches SAM 530914 and the new dispatcher,
then the original PropertySource override and Collection size/contains methods.
Four real OS threads use normal Java Thread/FLS ownership and sixteen distinct
Function objects. All three runs pass twelve cleanup checks and unchanged-input
checks. The final local handoff is
`.boom/instance-function-component-v454-a/final-handoff-b.json`, SHA256
`48ce423b3543d687545364752a152d4efd20bbec5be1a91403543adee960f756`.

Wrong-type and null inputs retain built-in Context kinds 12/4 at SAM PCs 2/5;
this does not establish materialized Java exceptions or exact JDK messages.
A separately constructed real NPE remains byte-identical across factory and
interface pending guards. Functional receiver tests cover PropertiesPropertySource;
the other three source dispatch rows have not received equivalent execution
tests. This unbound Function retains no receiver field, and no capture-retention
GC result is claimed.

The first component fixture accidentally bound Collection.add 62420/table12398
as its contains observer. The returned unmodifiable Collection correctly threw
a Java exception. That failure is retained; its exact exception subtype was not
captured. A new component adds the already linked original contains thunk,
`boom_batch_call_4621_36_185`, for declaration 62415/table12392. All 267 object
references and the original worker remain unchanged; actual/canonical DLLs are
independently compared again. Expected values and error checks were not relaxed.

Actual original Main advances beyond the CP110 factory and stops at CP118,
`Set.addAll(Collection)boolean` adapted to a captured `(Set)Consumer` in the
same `reload()V` method, at original PC 51. The observation takes 35.031 seconds,
exits 86 without a timeout and passes cleanup flags 7, zero held monitors/registry
lock, unchanged inputs and all 117 tool identities. Its execution receipt is
`.boom/native-main-runs/v451-instance-function-a/execution.json`, SHA256
`24a1d530fc2d130e1509a84a728c412d271467a6eecc0fb7b41cd578fa62d801`.
Advancing beyond factory creation does not establish that Main has executed the
lazy stream's Function SAM; the isolated component provides that separate evidence.

The next 27-Class source append preserves every current26 record, ID and Class
byte. Independent bytecode checks pass for its captured Set field and Collection
argument cast at PC 6, interface invocation at PC 9 and discarded boolean result.
The adapter passes actual/canonical COFF and prefix checks. It reuses original
Set.addAll declaration 66277, thunk `boom_batch_call_5135_280_185` and table13030;
the complete 2,092-row table is retained. Unselected receiver Class/body gaps
remain visible and are not claimed executable. Runtime metadata, capacity/root
integration and a complete image run remain pending. Main Class initialization,
Main execution, help output, the client and world creation remain unfinished.

## Captured addAll Consumer execution

The 27-Class, 267-object image now passes independent whole-PE byte equality,
receipt SHA256 `3cb88934c43b1b0681cb945c82d60714a7c5f38dcae93e160973bb023b5c406e`.
The CP118 component retains the complete original Set table and calls through
Consumer, generated SAM 530917 and the original interface thunk. Original
HashSet constructors and observers verify union contents, repeated additions
whose boolean result is discarded, and separate captured Sets. Its four
scenarios report 56 basic, 2 pending-setup, 138 thread and 23 collection calls,
219 in total, plus two direct pending-guard calls. Four real OS threads use
normal Java Thread/FLS ownership and sixteen fresh closures. Each scenario
passes twelve cleanup checks and unchanged-input checks.

Wrong Collection arguments report built-in Context kind 12 at SAM PC 6; a null
captured receiver reports kind 4 at PC 9. Materialized Java exceptions and exact
JDK messages are not established. A real original typed NPE remains unchanged
across the two pending guards. A nonnull receiver with a null Collection was
not tested.

At quiescent collection boundaries, every round uses the complete fifteen root
spans plus one fixture closure root. The closure, captured Set, its HashMap and
two key Strings remain live across two collections. Withdrawing that root makes
all five fail the heap's membership query; reclaimed addresses are not
dereferenced. The final collection frees twelve objects, rather than claiming
that only those five existed. Properties, PropertySource and the temporary
Collection are not claimed captured. This verifies explicit quiescent
collection, not automatic or active-frame collection. The final local component
handoff is `.boom/set-addall-component-v473-a/handoff-a.json`, SHA256
`5c7f670b0712fdb954719c0d848e8ec4c1da2231718c1a522ac3e8d4072ba044`.

Actual original Main advances beyond CP118 and stops at CP119, a noncapturing
`()Predicate` factory for `Objects.nonNull(Object)boolean`, in `reload()V` at
original PC 67. The observation takes 25.703 seconds, exits 86 without a timeout
and passes cleanup flags 7, zero held monitors/registry lock, unchanged inputs
and all 117 tool identities. File mappings, leases and owned native allocations
are closed. Its receipt is
`.boom/native-main-runs/v477-set-addall-scoped-a/execution.json`, SHA256
`b22c56dff562377d11c74f596cdbc8f8441374125d1a505bf9ee1908bda6bc1e`.
Main Class initialization, its method body, help output, the client and world
creation remain unfinished.
