# Normal Class-based reflection array allocation

The experimental Windows x64 candidate binds the original
`java.lang.reflect.Array.newArray(Class,int)` and `multiNewArray(Class,int[])`
native declarations to [a MASM adapter](../native/providers/reflection_array_normal.asm.inc).
Its [RARP48/2 ABI](../native-config/reflection-array-normal-abi.json) uses the
current JCLS144/1 Class mirrors and RTYP/2 metadata. The earlier RARP48/1 and
legacy CMRP representation remain separate and are not reclassified as current.

The two original `Array.newInstance` Java wrappers execute unchanged. Generated
headers supply the actual normal Frame32 descriptors, current Class pool, heap
cell, type capacity, and read-only next-array rows. Each row contains a source
TypeDesc pointer, the next array type ID, and the component's rank. The adapter
resolves the real Class mirror, follows that graph, and calls the existing MASM
`boom_typed_multi_new` allocator. Array-valued components retain their existing
rank; only the requested dimensions are allocated.

The published kernel contains no fixed Java Class or method IDs. It does not
write Java Class fields from a host language, add native oop roots, change the
heap allocator, or fabricate missing TypeDesc records. Ordinary VM heap oops
are the pointer domain; header/range checks do not prove arbitrary interior
pointer membership. Automatic collection and dynamic array-type synthesis are
outside the verified scope. Missing predeclared array metadata returns the
explicit unsupported context.

## Actual verification

The frozen source projection used 109,945 type slots, 109,803 provided types,
56,205 next-array mappings, and all eight primitive components. Both native
Frame32 records and the actual JCLS pool header/pointers were independently
checked against current COFF. Actual and fresh canonical native/service units
matched in code, data, flags, symbol auxiliaries, relocations, and unwind data.
The service's only public definitions are its function, pool, and row table.

The original single-dimension Java API completed 45 valid cases: eight
primitive types, Object, String, Runnable, and array-valued components, each at
length 0, 1, and 3. Array Class name, component Class name, length, zero/default
elements, and Class identity matched the locked JDK reference. Those cases made
270 original Java calls, used 45 real Class mirrors, and performed 60 array
opcode reads.

Four additional original multidimension API cases matched the complete JDK
array tree, including each allocated layer and default leaf values. Their
component run made 96 Java calls, loaded 12 normal mirrors, and read 10 defaults.
All three component runs completed System phases 1/2/3, used the real primordial
thread, and passed the twelve quiesce/close observations. The published fragment
also rebuilds to the complete COFF of that actual tested service.

The 21 single-dimension and 12 multidimension invalid-input cases checked only
builtin Context categories and ordering. They do not prove typed Java Throwable
objects or exact exception messages. Two rank-254 cases were not executed
because their Class metadata is absent. `Array.getLength`, generic get/set, and
primitive accessors are separate unimplemented native members, not coverage
implied by this allocation candidate.

## Main integration boundary

A separately verified 232-object native Main image used this adapter and the
reason-aware Inflater service. Its actual process passed the previous
`Array.newArray` diagnostic and reached a builtin Context7 at bytecode 189 of
`ServiceLoader$LazyClassPathLookupIterator.nextProviderClass`. That bytecode
calls `Iterator.next`; the actual receiver and rejecting runtime branch remain
under investigation. This observation does not attribute the new error to the
array allocator.

That process exited with 70. Heap destruction returned failure, and an earlier
snapshot recorded one outstanding monitor acquisition or waiter. Registry and
frame teardown had already occurred; heap, remaining resource-owner and RW
cleanup did not finish. A new entry guard checks monitor/registry-lock state
before destructive teardown and records heap-destruction failure explicitly;
it has passed source and full COFF checks but has not yet run in Main.

Main class initialization, its body, help output, the client window, and a world
remain incomplete. These sources remain outside the registered 35-provider
set. Generated tables, original inputs, test receipts, and temporary Python
orchestration stay in ignored `.boom`.
