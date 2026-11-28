# Original Class enclosing-method metadata

The new native candidate implements
`Class.getEnclosingMethod0(): Object[]` in assembly. It uses the original
`EnclosingMethod` Class attribute, including its `NameAndType` constant.
The earlier compiler naming projection retained only the enclosing class;
that projection alone cannot implement this native method.

The reusable source library is
[`enclosing-method-source.py`](../scripts/enclosing-method-source.py).
Its catalogue, metadata and rendering APIs take explicit original source,
normal Frame, packed layout and runtime-type inputs, plus an optional
generated expansion. They rebuild the attribute directory from hash-checked
Class bytes. An optional existing full source verification is bound to its
exact selection. Source generation does not run an assembler or accept a
runtime. The implementation is
[`enclosing_method.asm.inc`](../native/providers/enclosing_method.asm.inc),
with its contract in
[`enclosing-method-abi.json`](../native-config/enclosing-method-abi.json).

No attribute, primitive types and arrays return null. An attribute with
method_index zero produces a fresh normal `Object[3]` containing the
canonical enclosing Class mirror and two null elements. A nonzero method
index produces a fresh array containing the enclosing Class and fresh
normal Strings for the original method name and descriptor. The name
can be `<init>`; it is not inferred from a dollar sign in a class name.
Modified UTF-8 constants are decoded and projected as UTF-16 code units.
The String factory uses the actual compact-String configuration and normal
String layout and emits Latin-1 or UTF-16 storage. The original attribute
names and descriptors in this input are all ASCII; native execution of
non-Latin attribute text has not yet been verified.

Holder identities follow the source defining-loader namespace. A metadata
query does not initialize the represented class or its enclosing holder.
Unknown or unavailable source metadata is an explicit unsupported result,
not an invented absence of the attribute. The raw source directory covers
53,660 original classes and the 23 existing generated classes; its 109,968
type rows separately record absent, method, class-only and unsupported cases.

The candidate retains the original native Frame32, Java bodies, layouts and
existing root spans. It uses the existing normal heap and canonical Class
service. String class initialization, if needed, occurs before temporary
result allocation. After that point all calls are noncollecting assembly
services. This relies on the current explicit quiescent nonmoving collector;
it is not a root protocol for automatic or concurrent collection. Failed
partial results remain owned by the normal heap. Existing pending Context32
and its opaque VM plan are preserved.

Original Class, source selection and normal Frame checks show that the
related Java wrappers and helper class are already selected. No new Java
source selection or full source-verification run was required. The two new
native units passed actual/canonical source and complete COFF comparison.
An isolated JDK reference passed 21 cases in both tested modes, including
fresh results, method_index zero, cold classes and separate loader identities.
That reference is a development oracle, not the delivered game runtime.

The 264-object original Main image passed complete PE comparison against an
independent relink. An actual owned-process run passed the old enclosing-method
stop and reached `Class.getDeclaringClass0()`, diagnostic row106630. It exited86
without timing out, with cleanup flags7, no held monitor acquisitions and an
unlocked monitor registry. The execution SHA is
`71d50723adb6a2823214adec60d9b79b2939ceb419579ac190e76e6909140eba`.
Main class initialization, the Main body and help output did not complete.

The native component made 119 original API calls: 51 basic calls, six public
Method/constructor classification calls, 58 calls across four OS workers and
pending Context checks, and four calls in two real small-heap OOM cases.
Observed cases include absent attributes, primitive and array Classes,
method/class-only/constructor attributes, fresh results and unchanged cold
target/holder initialization state. The workers used original Thread/FLS
state, produced 16 distinct result arrays and preserved typed pending
Context32 with a nonzero opaque VM plan. All five runs completed normal
resource cleanup with unchanged inputs.

One OOM case exhausted the actual heap before the result array. The other
left exactly 64 bytes, allocated the real result array, then failed String
allocation with kind3. Neither case used a simulated allocator failure.
The public enclosing-Class component covered the attributed path; its
attribute-absent fallback through `getDeclaringClass0()` remains unfinished.
Complete Minecraft Main, client and world startup remain unfinished.

Component execution hashes:

- Basic: `a52487bab8029210923827ab7d135e4e2aa18d2128d42249a3388ebe67e8c762`.
- Public classification: `846f31b6e40a30d070bd804e3a92da323b675e2806f7c87af5b0c1396a5280b0`.
- Threads/pending: `c27ca8b5d9737bb7efe71f0e5bfb3804dede574bea166f6d0f27151c2fe75d2f`.
- Array OOM: `acde4b5c35b7492bac32029bd44c0f3444a59199746d5dceaba6d932094bd516`.
- Partial-result OOM: `cbdbc14f55ef05966a9027bd7bfe42832f470285e52d4056f9208f18af1cfd19`.
