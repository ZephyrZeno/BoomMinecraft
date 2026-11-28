# Original Class declaring-class metadata

The new assembly candidate implements `Class.getDeclaringClass0(): Class`.
It uses original `InnerClasses` and `EnclosingMethod` attributes and actual
defining-loader identities. It does not infer membership from a dollar sign,
nest host or enclosing-method owner alone.

The reusable source library is
[`declaring-class-source.py`](../scripts/declaring-class-source.py).
It accepts explicit original source, normal Frame, packed layout and runtime
type inputs, with an optional generated expansion. It rebuilds the directory
from the original Class bytes and binds an optional existing full source
verification to its exact selection. The implementation is
[`declaring_class.asm.inc`](../native/providers/declaring_class.asm.inc),
with its contract in
[`declaring-class-abi.json`](../native-config/declaring-class-abi.json).
Source rendering does not assemble, execute Java or accept a runtime.

The receiver must have its own matching `InnerClasses` entry. A nonzero outer
index takes precedence and identifies a member class. Only when that entry
has no outer does the native query try its `EnclosingMethod` owner, identifying
a local or anonymous class. Before returning, it checks the outer class's
reciprocal `InnerClasses` entry with resolved Class identities. A consistent
member returns the canonical outer Class mirror. A consistent nonmember
returns null after the check. Primitive, array and no-outer cases return null.
The represented and declaring classes are not initialized by this query.

The readonly source directory contains 109,968 type rows from 53,660 original
classes and the 23 existing generated classes. It records 21,845 consistent
members, 7,125 consistent nonmembers, 80,845 null cases and 153 explicitly
unsupported metadata cases. Unavailable resolution is not an invented null
or a fabricated linkage error. This is source coverage, not execution of
every row.

The DCLR160/1 contract retains the original native Frame32, Java bodies,
layouts and existing root spans. Canonical mirrors use the existing assembly
Class service and its root bank. The error helper uses the selected original
`IncompatibleClassChangeError(String)` constructor and normal Throwable
protocol. Successful error construction restores the incoming pc, method and
depth before publishing the pending exception; constructor failures retain
their actual error origin. Existing pending Context32 and its opaque VM plan
are preserved. The implementation supports the current explicit quiescent
nonmoving collector; automatic or concurrent collection remains unfinished.

The two new units passed actual/canonical source and complete COFF comparison.
The related original Java wrappers and exception constructor were already
selected, so no new Java selection or full source-verification run was needed.
An isolated JDK reference passed 25 cases in default and interpreted modes,
including members, local and anonymous classes, separate loaders and cold
classes. Five deliberately inconsistent development inputs produced exact
native/public ICCE results. An array outer was rejected earlier by class
loading with ClassFormatError, before entering the native query.

The locked production directory contains no ICCE disagreement rows. Its
error helper has not been executed by an AOT negative fixture; the JDK
development cases do not establish that coverage. This native does not
implement invalid Classfile admission.

The 266-object original Main image passed complete PE byte comparison against
an independent relink. An actual owned-process run passed the declaring-class
stop and reached the captured `Set -> Predicate` LambdaMetafactory call at
class52050/CP53, diagnostic row5187. It exited86 without timing out, with
cleanup flags7, no held monitor acquisitions and an unlocked monitor registry.
The execution SHA is
`c6a83cd32c4174062293fe458ac329a92f6c98750ff9d508150b7292abc6f1b8`.
Main initialization, its method body and help output did not complete.

The native component passed 164 original API calls: 88 basic calls, 74 calls
for four OS threads and pending Context checks, and two calls with a genuinely
exhausted heap. The cases cover member/interface/application/local/anonymous,
primitive and array Classes, canonical holder identity and repeated warm
queries. All three runs completed normal resource cleanup with unchanged
inputs. The workers used original Thread/FLS state and preserved typed pending
Context32 and an opaque VM plan.

The OOM process started with the application holder's canonical mirror cell
empty, exhausted the real arena through a successful byte-array allocation,
then observed kind3 on two fresh native calls. The holder cell remained empty
and the JCLS lock was released after each failure. No allocator error was
simulated. Application class initialization state was not observable in this
legacy component image and is not claimed as a state0 test; available JDK
Class descriptors were observed separately.

An additional `getSimpleName(Map.Entry)` experiment stopped at an unresolved
source dependency with kind45057. Its one call is excluded from the 164 passed
calls. Broader class naming is still unfinished. Earlier component preparation
and observer failures were retained separately; they did not alter the native
candidate or weaken link verification.
Complete Minecraft Main, client and world startup remain unfinished.

Passed component execution hashes:

- Basic: `cbeda8128c042eec02ea32bdcd85a9435cf2c0392e68a690c4b70c8a19447127`.
- Threads/pending: `76151128490e5b14cc96ffe442f516606bd82bc71b82b6f6b20fdb481429cefb`.
- Cold-holder OOM: `abe4cb0bd50b1a52bed6b733709d71cd66e49636c05b4fd17e84b63c46532396`.
