# Ordinary static MemberName resolution

The assembly runtime can resolve ordinary `REF_invokeStatic` MemberNames in
the known source loader namespaces. It creates normal ResolvedMethodName
objects and returns method metadata. DirectMethodHandle invocation,
`invokeBasic`/`linkTo`, CallerSensitive caller binding and complete Minecraft
startup remain unfinished.

## Source and runtime

The reusable source library is
[`method-handle-method-source.py`](../scripts/method-handle-method-source.py).
Its inputs are the original summary, classes, selected closure, Frames,
layouts and normal-method catalogue. Its metadata/render API emits source;
it does not assemble, execute Java, register a provider or mark a VM ready.
An optional completed source verification is separately bound to the exact
selection; prepared metadata without it remains unverified source preparation.

The original projection covers 53,660 classes and 453,353 ordinary method
rows, with original names, descriptors, slots, MethodIDs, modifiers and trusted
CallerSensitive annotations. Loader IDs and descriptor namespaces come from
the ordered `summary.class_literals.loader_keys`. For the current input these
are `bootstrap`, `platform`, `vanilla-application`; an invented `app` alias is
not accepted. The original Java bodies, native Frames and Java object fields
are not replaced or expanded by this service.

The three assembly fragments provide native ownership, source method lookup
and resolution. The ABI is documented in
[`method-handle-method-abi.json`](../native-config/method-handle-method-abi.json).
The native registration table changes only the resolve and VMInfo handler
targets. A proof-only inverse restores those two symbol names and matches the
complete original COFF. Existing field handlers retain their actual objects.

Resolution performs symbolic lookup, caller/member access checks, staticness
and known-loader descriptor constraints before publication. CallerSensitive
comes from original source annotations. The declaring holder is not initialized
just to resolve its method. The normal RMN class is genuinely ensured and its
ordinary zero-payload object is allocated without calling its Java constructor.
No HotSpot-injected `vmtarget`, `vmholder` or `vmindex` field is added to Java
layouts. Native side records represent that VM metadata.

## Ownership and roots

The owner has 4,096 records of 128 bytes and an explicitly registered bank of
8,192 strong oop cells. A LIVE record roots its normal RMN and actual holder
Class mirror; canonical identity is original MethodID plus source epoch, with
no caller captured as canonical authority. PREPARING records temporarily root
normal VM results across callbacks. Native tokens contain indices/generations,
not hidden oop fields. Publication and scratch operations use assembly locking;
no such lock is held across original Java/Class initialization callbacks.

Method VMInfo follows the original native allocation order: a fresh normal
`Object[2]`, real Long class initialization, then a fresh normal Long allocated
and filled through its original value field. It does not call a Long constructor
or `Long.valueOf`. Element0 is Long(-2), the source nonvirtual static index;
element1 is the same input MemberName. The array has a temporary strong root
across Long initialization, and scratch release runs with pending Context too.

The entry opens the owner before VM/System Java. After all callers/workers have
ended, a read-only real heap monitor/registry-lock gate precedes owner close;
root snapshots and registry/frame/heap destruction follow it. Busy ownership
retains records, roots and heap state instead of forcing cleanup. Main uses
15 complete spans; the existing 115 generated-Lambda cells, one new ordinary
class failure cell and 8,192 new native cells are counted separately. This
supports explicit quiescent nonmoving collection, not automatic/concurrent GC,
weak RMN caching, dynamic unloading or redefinition.

## Observed validation

The initial B generator used the wrong application loader spelling. Its
NULL-caller String component passed, but the actual original Main failed with
kind20 and one held monitor. A fresh owned-process observation, exact linked
instruction/COFF comparison and the actual caller52041 ClassRow64 identified
loader=-1/status0. The same original ServiceLoader request succeeded with a
NULL caller and failed with the real application caller despite correct live
loader/module identities. Those failed records remain separate evidence.

C derives the real loader keys and regenerates only source metadata. Its
instruction, unwind and original field paths remain unchanged. The exact
ServiceLoader case passed with both NULL and real PropertiesUtil$Environment
caller95: same MemberName return, CallerSensitive flags0x06110009, shared
canonical RMN and normal VMInfo, while ServiceLoader remained uninitialized.
That worker made 19 original calls, with execution SHA
`a0dd9d13717d8e234d578d4a864caa179d1a9d4e08d32422d8398598eb9a2963`.

Eight real OS workers with original Java Thread/FLS completed 71 original
calls, shared the canonical RMN and produced 16 distinct VMInfo arrays and
Long boxes. Pending Context32 remained unchanged; temporary records and all
owner roots were released on normal close. Execution SHA is
`6eab9d296fb44c3d71864d9f5f3421dbb369ec0c29deb4709959e5906546baf5`.
Thirteen negative/opaque cases made 41 original calls and checked supported
NSME/access/staticness order, speculative NULL, pending Context and an opaque
VMplan token, with SHA
`2d50873dfcbd2bb5d0dd7af050d52cf8599b3b03f6ad6898b3a91c57669b405f`.
Error messages remain generic rather than full JDK diagnostic text. All three
workers reported the complete resource cleanup and unchanged inputs. These
component counts do not establish game performance or full MethodHandle use.

Two further workers exercised actual heap exhaustion without injected failures:
zero remaining bytes prevented the array allocation; 48 remaining bytes allowed
the real array before the fresh Long allocation failed. Each made eight original
calls; pending OOM Context3 survived, PREPARING records/users returned to zero
and all resources/owner roots closed normally. The respective execution SHAs
are `2f49a2e0ee12ccdcf2a7c89151e4f7c6e8b6d8733e70e82177ccee658731ab33`
and `078ee31aa63c172458cc5d31168b99eb98d42f3047cfa4dbb7f860950ce8cf71`.
Long was already initialized in these workers; they do not provide cold Long
initialization coverage. The five C workers total 147 original calls; the older
B String worker's 21 calls remain separate evidence.

The C Main has 260 objects; independent complete PE relinking passed. Its
actual observation SHA is
`e9561b66970a0abe2dabdbcc86b4990da25970abbe6d1f459b7e0c1b204642b1`:
guest exit86, cleanup7 and zero held monitors/registry lock. It passed the
previous resolution gap and stopped at original native
`PreviewFeatures.isPreviewEnabled()Z`, method112717, linked diagnostic row50678.
Main class initialization/body/help, client window and world startup are still
incomplete; exit86 is a retained diagnostic stop, not successful game startup.

Inherited maximally-specific interface selection, nonstatic/constructor and
signature-polymorphic method resolution, custom/generated loader namespaces,
callable handles and caller binding remain explicit unsupported domains. Full
loader transformation, invalidation and unloading need their own integration;
a fixed-image metadata result does not authorize reuse across those boundaries.
