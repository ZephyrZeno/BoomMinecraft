# Normal Class lookup and real missing-class exceptions

This experimental Windows x64 MASM candidate binds the original
`Class.forName0(String,boolean,ClassLoader,Class)` and
`ClassLoader.findBootstrapClass(String)` native declarations. The existing
normal Frame32 envelopes, JCFN128/1 lookup data, and original Java method bodies
remain the source of their identities.

The subsequent [built-in loader candidate](CLASS_LOOKUP_BUILTIN.md) adds
prelinked platform/application lookup with separate tests and Main evidence.
The bootstrap and validation-only results below retain their original scope.

The [lookup kernel](../native/kernels/class_lookup_cnfe64.asm.inc) and
[exception helper](../native/providers/class_lookup_cnfe_throw.asm.inc) use
[read-only callback metadata](../native-config/class-lookup-cnfe-abi.json).
They contain no fixed Java Class or method IDs. A source generator supplies
the original ClassNotFoundException descriptor and layout, its String
constructor, the current type map, the Throwable descriptor, and the original
`String.replace(char,char)` method.

## Loader argument correction

The original nonnull-loader validation reversed two arguments to
`boom_runtime_instanceof`. Its ABI requires the runtime type map in RDX and the
target TypeDesc in R8. The old call supplied the ClassLoader TypeDesc from
JCLS144+112 in RDX and the RTYP map from JCLS144+40 in R8. The candidate uses the
correct order.

This was observed in the actual native Main process with a hardware data
breakpoint on its own Context32 kind field. The first write of kind7 occurred
inside `runtime_target`: the map check received a TYPE/1 descriptor. The
captured registers, JCLS fields, complete private function bytes, and linked
module addresses agree. No preceding kind16 write occurred on that Context.
The debugger changed only CPU debug registers.

Correct argument placement validates a nonnull ClassLoader object. Resolution
through system, platform, or arbitrary custom loaders remains explicitly
unsupported in this candidate; successful validation does not mean loading
through that loader has been implemented.

## Missing-class construction

The old ordinary bootstrap miss set kind16 without a pending Throwable object.
The candidate instead calls the original Java String replacement method,
allocates a normal ClassNotFoundException, invokes its original String
constructor, and publishes the real object through `boom_exception_set32`.
An existing error is preserved, and allocation or constructor failures
propagate without clearing the original Context.

Bootstrap lookup uses dot-to-slash conversion for the exception message.
The caller's String is unchanged. The separate `findBootstrapClass` operation
continues to return normal null on a miss.

The 48-byte callback table contains six pointers:

| Offset | Source-derived binding |
| --- | --- |
| 0 | ClassNotFoundException class descriptor |
| 8 | ClassNotFoundException object layout |
| 16 | Original String constructor |
| 24 | RTYP runtime type map |
| 32 | Throwable TypeDesc |
| 40 | Original String.replace(char,char) |

Bindings share the lookup pool's source, loader, transform, and layout
generation. They must be regenerated when that generation changes.

## Actual verification

The bootstrap exception candidate completed thirteen native component cases:
two successful Class lookups and eleven missing-class cases. The original
`forName0` native frames and original exception getters made 141 calls.
Actual exception type, Throwable assignability, message, cause, legacy
`getException`, and unchanged input content matched the locked JDK reference.
Unicode, empty, slash-containing, and embedded-NUL names are included in this
bounded ordinary-name set.

That run completed System phases 1/2/3 with the real primordial thread, checked
the separate bootstrap-find operation, and passed all twelve owner shutdown
observations. It did not invoke the public `Class.forName` Java wrapper with an
invented caller or run Minecraft Main.

The combined candidate adds the loader argument correction to that exception
implementation. The two loader-load displacement bytes are its only machine
changes from the bootstrap exception candidate. A separate native component
then checked four nonnull-loader inputs and two bootstrap regressions, making
44 original method/frame calls. The system and platform loaders came from
their original Java getters; the system parent was exactly the platform
loader, whose parent was null. The four nonnull inputs reached the explicit
unsupported kind20 instead of the old protocol kind7. Both bootstrap
regressions and all twelve owner shutdown observations passed.

Complete actual/canonical COFF comparisons cover code, data, section flags,
symbol auxiliaries, relocations, and unwind records. The published fragments
reconstruct the full combined service source and its complete COFF.

A separately verified 234-object native Main image used the combined service.
Its actual process passed the former protocol failure and stopped at the
nonnull-loader kind20 boundary. Main class initialization and its method body
remain incomplete. One held monitor prevented heap teardown; the guard
reported status170 and retained registry/frame state. Cleanup was not accepted.
Client startup and world creation remain unverified.

## Remaining scope

The candidate is not a completed ClassLoader implementation or a promotion of
the pending native provider set. Nonnull-loader resolution, new or missing
array identities, dynamic class definitions, transforms, and mod compatibility
remain work in progress. The other thirteen cases from the initial reference
set were not executed by the bootstrap native component.

Managed temporary objects stay on the native stack under the current
nonmoving heap contract, which forbids collection during active Java/native
frames or external calls. The candidate adds no persistent oop roots and
provides no automatic or concurrent collector protocol.
