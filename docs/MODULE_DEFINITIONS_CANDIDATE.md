# Normal Module definition and native read/export graph

The independent candidate binds the five original private static natives of
`java.lang.Module`: `defineModule0`, `addReads0`, `addExports0`,
`addExportsToAll0`, and `addExportsToAllUnnamed0`. Runtime execution is ASM.
Method IDs, frames, source field offsets, loader statics and package inventories
are derived from the locked original inputs. The candidate does not register a
shared provider or change runtime572.

The native boundary follows the locked
[Module.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/Module.c),
[modules.cpp](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/classfile/modules.cpp),
and [javaClasses.cpp](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/classfile/javaClasses.cpp).
The source model seals these files, the JVM entry delegates, module/package entry
implementations, package syntax checks and original Java bootstrap sources.

## Object and graph model

The original 117-byte named Module constructor writes layer, name, loader and
descriptor before calling `defineModule0`. The native allocates no Module and
does not write those Java fields. It registers that same normal Java object with
`boom_java_class_bind_module`, using the normal image's JCLS pool. For java.base,
that existing ASM service also repairs already allocated Class mirrors; sealing
then ends the permitted early java.base-unbound phase. The old MODU3 development
object factory is never used. BootLoader's original unnamed Module slot remains
separate.

Every named JCLS key is checked against its locked module-info SHA, parsed
`ModulePackages` constants, resolved loader and class catalog package ownership.
The runtime validates exact membership of the locked package set before publishing
a new definition. A definition outside that package/module/loader profile is an
explicit context20 boundary. Syntax errors and supported duplicate/error cases
use original typed Java exception constructors.

JMOD112/1 refers to the existing JCLS pool and heap, immutable module/package
keys, source loader statics, a normal String factory and mutable native records.
Module records are 64 bytes. Read edges use low/high 64-bit words at offsets 8/40;
all-unnamed and individual unnamed-loader bits remain distinct. Package records
are 32 bytes with unqualified, all-unnamed, individual unnamed-loader and low/high
qualified export state. Capacity is 128 JCLS identities. Graph-only unnamed
identities are 128 through 130, so appended named slot 64 cannot collide with an
unnamed identity. One SRW lock serializes mutations; read predicates use its shared
mode. The graph predicates expose actual stored permissions, rather than inferring
success from a zero native return value.

Version and location are copied as bounded UTF16 metadata into native image
storage, preserving null separately from empty. These records contain no retained
Java oops and need no new Java GC roots. Temporary native memory is owned per call
and released on success, duplicate definition, error and unsupported profile.
Registry, heap, class state and image share one lifetime; unloading/rebinding the
same image into another heap is outside this scope.

The java.base/null-loader path never initializes ClassLoaders. Non-null loaders
must equal the real completed Java `PLATFORM_LOADER` or `APP_LOADER` publication.
Existing `boom_java_class_bind_loader` publishes that identity. For application
loaders, the generated inherited FMAP reads original `ClassLoader.unnamedModule`;
the normal Module, null name and same loader are checked, and that same object is
bound to the existing app unnamed JCLS slot. Platform loaders have no unnamed
slot in this batch; their ordinary managed loader-to-module field remains the GC
edge. No replacement Module or bootstrap unnamed alias is created.

HotSpot's injected ModuleEntry accessor falls back to the loader's unnamed entry
when a normal Module has not been defined, even if a white-box constructor gave
it a name. The candidate preserves this native-entry distinction. It does not
manufacture registration from `Module.isNamed()`. Pending errors remain intact.

## Executed scope

Final 64-slot source/frame/ASM/COFF candidate:
`.boom/module-definitions/source-v147-g/candidate.json` and `verification.json`.
Final component:
`.boom/module-definitions/execution-v147-h/execution.json`.

The component retains all original Java COFF, descriptors, root banks and class
initializers from the historically verified normal source selection. Only the
five exact category-2 native stop procedures are removed in an isolated object;
all complement bytes/procedures and diagnostic row data are checked. The added
candidate and full canonical LINK response are sealed. Later relink/recheck
manifests explicitly identify the prior image, original inputs and newer harness.
They do not rewrite the original proof or claim a current full formal selection
verification for the extra candidate image.

Executed checks include:

- Original HashSet, nonstrict ModuleDescriptor.Builder and named Module Java
  constructors for java.base and java.logging. The nonstrict builder is the
  original bootstrap descriptor path; no host field writes are used.
- Same java.base oop in JCLS slot 0, two repaired early Class mirrors and the
  end of early binding. ClassLoaders stays in state 0 throughout the null path.
- All five framed natives; reads, specific unnamed targets, all unnamed targets,
  qualified exports, unqualified exports and all-unnamed exports. Native graph
  observations are separate from Java fields updated by higher Java wrappers.
- Sixteen exact locked-JDK typed error/message comparisons, including null order,
  missing package normalization, malformed package syntax, java.base InternalError
  and other-module IllegalStateException duplicates.
- Eight OS threads making 1,024 read/export mutations, and a separate eight-thread
  definition race with exactly one original Module published and seven original
  duplicate exceptions. Distinct Unicode version/location inputs prove that the
  winner's symbols survive losing calls.
- A valid Java module outside the closed profile returns context20 and leaves
  all graph records and JCLS Module roots unchanged.
- Two explicit quiescent collections using nine normal source root banks,
  1,183,760 physical cells and no extra test handles. The original JCLS roots
  retain all three defined Module objects; graph state and banks remain intact.
  Native owned buffers return to zero and the heap is destroyed.

These are development OS threads; the component does not claim Java Thread.start,
automatic/concurrent GC or a completed VM bootstrap. It does not exercise the
non-null platform/app loader publication path. That path must be observed by the
owned bootstrap prefix/formal integration. It does not claim the complete dynamic
module/layer, transformation, unloading, instrumentation or mod invalidation
protocol. Those changes require a new module/loader/package identity contract and
cache invalidation; unknown profiles remain explicit gaps.

The first public strict Builder experiment stops at original
`ModuleDescriptor.Builder.packages` invokedynamic PC 17 before reaching the native.
That failure remains in `execution-v147-a`. The component uses the original
nonstrict bootstrap constructor rather than rewriting that Java instruction or
claiming lambda lowering was fixed.

The old verified JCLS has 64 entries: 62 named modules, app unnamed and boot
unnamed. Its resolved graph additionally requires the package-empty
`jdk.jdwp.agent` module through jdk.jdi. The separate 65-slot physical candidate
is not treated as a verified runtime input here. Pure model checks accept its
new slot 64, 63 named modules and two edge words; actual 65-slot execution and the
Boot provider's exact-capacity rebuild belong to the next verified transition.

The primary agent independently rebuilt the frozen source candidate and ran the
complete component over the newer, fully verified formal28 source/native
baseline. The source receipt is
`.boom/module-definitions/root-review-source-v148-a/verification.json`, SHA256
`784d53572c15c2c70cf70d8ef62673375f9f78b2e757ba74beb5549823326cff`.
The successful execution is
`.boom/module-definitions/root-review-execution-v148-a/execution.json`, SHA256
`e96afe49023b978035571552a9d86da3075001d89d5bfa52a73dd31e10a8c850`.
The original constructors, publication, error oracles, concurrency and GC checks
passed. This remains a 64-slot component; the nonboot loader/unnamed publication
branch and a 65-slot owned bootstrap are still explicitly unexecuted here.

## Commands

```powershell
python scripts/module-definitions-candidate.py `
  --state .boom/accepted-native-three-families-v146-26.json `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/module-definitions/source-fresh

python scripts/test-module-definitions.py `
  --candidate .boom/module-definitions/source-fresh/candidate.json `
  --selection .boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000 `
  --native-manifest .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/vm-entry.json `
  --native-execution .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/execution.json `
  --output .boom/module-definitions/execution-fresh
```

Use fresh project output directories. `--relink-images` retains original Java and
remaining-stop COFF and replaces only the separately verified candidate object.
`--recheck-images` pins a new harness over identical sealed native bytes.
