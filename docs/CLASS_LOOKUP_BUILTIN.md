# Prelinked lookup through the original built-in loaders

This experimental MASM candidate extends the
[bootstrap Class lookup candidate](CLASS_LOOKUP_CNFE.md) to the original
platform and application loader singletons. It resolves names from the locked
input catalogue. General Java `ClassLoader.loadClass` dispatch,
`findLoadedClass0`, `defineClass`, and arbitrary custom loaders remain separate
unimplemented protocols.

The original native Frame32 envelopes still call a MASM service. Its
[core](../native/kernels/class_lookup_builtin64.asm.inc),
[namespace helpers](../native/providers/class_lookup_builtin_namespace.asm.inc),
and [exception helper](../native/providers/class_lookup_builtin_throw.asm.inc)
contain no fixed Java Class or method IDs. Source-derived declarations and
read-only tables supply the concrete bindings.

## Lookup and identity

The [JCLG128/1 layout](../native-config/class-lookup-builtin-abi.json) supplements
the original JCFN128/1 pool. It references the real ClassLoaders descriptor,
original PLATFORM_LOADER and APP_LOADER static cells, the current JCLS144 pool,
and the original `ClassLoader.getUnnamedModule` Java method. Identity checks
require the original initialized ClassLoaders state and the actual published
singleton oop; an unrelated loader is not treated as bootstrap.

Lookup searches bootstrap, then platform when allowed by the requested loader,
then application when requested by the application loader. The supplemental
catalogue contains 4,381 platform and 32,366 application scalar names. Rows
are ordered by unsigned Java String hash and UTF16 name. Known names whose
metadata is unavailable retain explicit unavailable flags; they return kind20
instead of a fabricated ClassNotFoundException.

The matched type's actual defining loader and module determine the mirror
bindings. Requesting String through the application loader still returns the
bootstrap-defined Class. Requesting java.sql.Driver through the application
loader returns the platform-defined Class and java.sql module. An application
Class uses the actual application loader and its original unnamed Module.
The service obtains that Module through the original Java getter and existing
normal JCLS bind services, rather than allocating a replacement Module.

After the permitted namespaces all report a genuine miss, one real
ClassNotFoundException is created. Bootstrap messages retain the earlier
dot-to-slash conversion; known nonnull-loader messages retain the original
ordinary binary name. No intermediate exception is cleared to try another
namespace. Target initialization continues through the original InitRow16
and class-ensure machinery.

## Actual verification

Ten native component cases passed against locked JDK references. They used
the original native `forName0` frames and original Java getters, with 126
method/frame calls:

- System and platform requests for String returned the same bootstrap Class
  and java.base module.
- System and platform requests for java.sql.Driver returned the same platform
  Class and java.sql module.
- Ordinary missing names produced real ClassNotFoundException objects with
  the correct message for the requested namespace.
- Bootstrap lookup rejected the platform class and retained successful String
  lookup.
- A system request for the original net.minecraft.server.Main returned its
  Class mirror with the real system loader and exactly the Module returned
  by the original system getUnnamedModule getter. A platform request for that
  name produced the expected real exception.

The application Class bytes used by the JDK reference were checked against
the original input plan and jars. The native component used initialize=false:
Main's native ClassDescriptor state remained zero, and neither Main nor its
class initializer was invoked. The test host did not write Java fields,
Class state, or loader objects.

The component completed System phases 1/2/3, used the real primordial thread,
and passed all twelve owner shutdown observations. Actual and canonical
objects matched in complete code, data, flags, symbol auxiliaries,
relocations, and unwind records. The published fragments reconstruct the
actual service and its complete COFF. These checks do not establish concurrent
lookup behavior, full class loading, or game startup.

## Original Main progression

A separately verified 234-object native Main image used this candidate.
Actual execution passed the previous nonnull-loader kind20 boundary and
reached the original SLF4JServiceProvider class initialization. It stopped at
the verified source-selection row for that unselected initialization, using
the diagnostic kind45057 and process exit86.

That run reported zero held monitors, cleanup flags7, and completed heap,
registry, frame, jimage resource, and native-memory cleanup. Its original
error Context was retained. Main class initialization and its method body
still did not complete.

The next source selection automatically added 38 original classes and 108
Java methods. Its full source verification covered 71,884 original Java
methods and retained all 71,776 previous Code/source records and 192,738
previous generated function hashes. These are selection and verification
counts, not executed-method counts.

The new source was bound to the assembly services and a 233-object, 42-role
Main image with 13 physical root spans. Independent complete PE relinking
matched byte for byte. This image uses the new source's original dispatch;
the previous temporary SLNX observer and single-thunk diagnostic replacement
were omitted.

Actual execution passed the previous provider-initialization selection stop
and reached a lazy dispatch target in the original logging library:
org/apache/logging/log4j/MarkerManager$Log4jMarker.setParents(Marker[]).
The next stop was unselected method501208, diagnostic row130263, kind45057,
with caller method511277 at pc1 and natural process exit86. The original
method already has generated assembly; it needs source selection and linking.

This run again reported zero held monitors, cleanup flags7, all jimage pins
and leases released, and 35 native-memory allocations matched by 35 frees.
Its source and execution inputs were unchanged. Main class initialization,
the Main method body, server help output, the client window, and a playable
world remain unverified or incomplete.

## Boundaries

Unknown custom loaders and nonnull-loader array names remain kind20.
Unavailable metadata does not become a missing-name exception. Class
definition, hidden or dynamically supplied classes, transforms, and mod
compatibility remain outside this candidate. Binding tables belong to the
same locked source, loader, transform, and layout generation and must be
regenerated when it changes.

The service adds no persistent oop or root span. Existing static/JCLS roots
retain the real bound objects. Native temporary oops rely on the current
nonmoving heap rule that forbids collection during active Java/native frames
or external calls. Automatic/concurrent collection and game performance
improvements have not been established by these tests.
