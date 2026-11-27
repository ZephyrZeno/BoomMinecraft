# Normal Object.clone assembly service

The original protected native `java/lang/Object.clone()Object` has a normal
Frame32 adapter and an assembly service. The service allocates a fresh normal
heap block of the same runtime type, then copies the payload. References remain
shallow; a clone does not run its Java constructor. Ordinary receivers must
implement the original bootstrap `Cloneable` interface. Arrays of primitive or
reference components satisfy that requirement, including nested arrays. These
rules follow the [Java 21 Object.clone contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#clone()).

The OCLN96/1 readonly pool binds the actual heap, RTYP and JCLS tables and
source-derived type/method symbols. The kernel requires the actual RTYP/JCLS
capacities to agree, without baking in a single-lambda or batch-lambda count.
The allocator creates the new header; the copy covers only the original
payload. There are no additional persistent oop roots or lifecycle owners.

A non-Cloneable receiver uses the normal Class mirror, original `Class.getName`
and original `CloneNotSupportedException(String)` constructor, then publishes a
real typed exception. Null and allocation failure retain the existing builtin
Context4/3 protocol; this does not establish typed NPE/OOME materialization.
An already exceptional or pending Context32 is preserved byte for byte.

`scripts/object-clone-source.py` is a reusable source projection and renderer.
It resolves classes, original bytecode, the native declaration and normal Frame
from explicit inputs, without numeric method/type IDs or local coordinator
dependencies. Its CLI writes fresh source artifacts under `.boom`, `target` or
`dist`; it does not assemble, register or execute a provider:

```text
python scripts/object-clone-source.py --batch-summary <summary.json> --classes <classes.jsonl> --source <closure.json> --frames <frames.json> --source-verification <completed-verification.json> --output .boom/object-clone/source
```

The two published renderings match the independently assembled candidate's
actual/canonical ASM and complete non-debug COFF. The output-directory guard
also rejects six invalid destinations before reading inputs or creating files.
The publication proof SHA is
`9ea5a083b642bcc47d9df744b8731fe1ca0b0ff13c507ce91988c9cbc15b1918`.

Actual native component verification covers:

- 26 cases, including all eight primitive array kinds, reference/nested arrays,
  original `ArrayList` construction/addition and its real Java clone fixup.
- Fresh identities, reference/scalar payloads, independent storage and monitors,
  source GC-mark isolation, typed CNSE/message and preservation of all Context32.
- Eight actual OS workers completing 512 clones, 545 normal original-method
  calls in total, and all 12 component cleanup checks passing.
- A separate 4096-byte heap that exhausts naturally after 64 fillers: the same
  production objects return builtin OOM3 without publishing or allocating a clone.

The immutable component handoff SHA is
`368170c4f72403b7768fa24b17596e0394ce854684b8ca0b65014d273d9409c3`.
The component retains its historical source selection; required callback
Class/Code hashes match the newer Main selection, which is not relabelled as
having executed here. The identity-hash Java API, automatic/concurrent GC and
whole-game performance were not tested. This remains an unregistered derived
service; the 117-tool provider identity and original Java Code are unchanged.
Component verification is separate from Minecraft Main, window and world startup.
