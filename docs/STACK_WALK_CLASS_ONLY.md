# Class-only StackWalker candidate

This unregistered development candidate binds the three original JDK21 natives
`checkStackWalkModes`, `callStackWalk` and `fetchStackFrames`. It does not change
the provider registry, 105-tool namespace, runtime DLL, Java Code or any previous
receipt. Source/ASM/COFF verification has passed. **Original Java callback
execution and native concurrency acceptance are still pending.**

`scripts/stack-walk-source.py` derives method IDs, private native descriptors,
Code hashes, normal inherited field maps, Class[] runtime type and prefix-skip
class IDs from the locked classfiles and existing metadata. It compares the
classfile ConstantValue entries with the local JDK21.0.13+3 `src.zip` and the
fixed OpenJDK native enum. `scripts/stack-walk-candidate.py` assembles the candidate
and independently reconstructs its model, source and actual COFF symbols. Its
verifier separately reassembles canonical source and compares every nondebug
section's bytes/flags, all symbol identities and normalized relocation targets,
including pdata/xdata. Matching exports alone does not pass this comparison.

The semantics references are the fixed-tag
[Java/native bridge](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/StackStreamFactory.c),
[VM walk](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/prims/stackwalk.cpp),
[stream lifetime](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/prims/stackwalk.hpp)
and [native constants](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/include/jvm.h).
Their complete hashes and the two original Java source hashes are pinned in the
model; local input files are under
`.boom/stack-walk/pinned-sources/jdk-21.0.13+3`.

The supported native mode is Class-only plus getCallerClass, value6. Values2,
4,32 and256 are independently checked as the corresponding Java/VM flags.
Other modes, continuations, live frames, generated-frame profiles and the
CallerSensitive exception branch produce explicit Context20. Malformed private
protocols produce Context7. These boundaries are incomplete JNI exception
semantics and are not reported as ordinary Java success.

The MASM implementation follows real TracePool3 TLS nodes and validates method
row bounds, PC, declaring type, class identity and Context. It initially removes
StackWalker, AbstractStackWalker and direct subclass frames, applies skipFrames,
and fills normal JCLS Class mirrors. Hidden frames are filtered in native code;
the intact original Java consumer performs reflection/MethodHandle filtering.
No Main class name or fixed caller identity is used.

The buffer reserves two elements. Slot0 holds the actual current registered
source Thread oop; slot1 remains untouched. The original private
`doStackWalk(JIIII)Object` receives the first batch, and its result is returned
unchanged. Later fetches advance past the previous last frame and return an end
index. A resized Class[] may copy the reserved Thread marker, as the original
Java implementation does.

Each native call owns a stack record. A generation is published in an owned
active list for the duration of the Java callback. Fetch looks up that generation
before using a record, checking OS identity, Context, source receiver, mode and
Thread marker. Distinct nested receivers can own simultaneous records. An SRW
lock protects only publication/lookup/removal; no lock spans Class allocation or
Java callbacks. Every callback exit removes its generation and clears the
original buffer's magic, including pending exceptions/stops. Transient oops have
the owning native/Java argument lifetime; collection remains explicitly
quiescent, and no automatic GC support is claimed.

The current independent build is `.boom/stack-walk/source-v150-b/candidate.json`
with `verification.json`. The earlier `source-v150-a` and source-model-only
directory remain historical. Eight boundary unittest cases verify the actual
constant/field contracts and reject changed machine instructions or swapped
undefined-symbol identities even when the COFF export/import sets are equal.

The console-only reference runner is `scripts/test-stack-walk-class-only.py`.
Its current sealed JDK oracle, `.boom/stack-walk/oracle-v150-b/verification.json`,
completed1025 original `DebugGraphics(Graphics)` constructions, including eight
OS workers with128 iterations each. Its class-initialization log confirms that
BufferedImage was not initialized. No headless property was set, no window was
created and no desktop automation was used. This is a JVM reference oracle,
not candidate execution. The source, compiled oracle class, tools, VM library,
module image and class-initialization log are sealed and rehashed after the run;
the first `oracle-v150-a` remains historical.

The original `(Graphics)` constructor calls the original no-argument constructor.
Those two real Java frames have the same DebugGraphics declaring class. The
no-argument constructor uses StackWalker and branches around BufferedImage when
that caller class equals the receiver class. A new focused current31 source
selection prepares these complete methods and StackWalker callbacks with the
normal thread bootstrap. Its proof and later native reports are separate from
the candidate's static proof. Reflection (`getDeclaredMethods0` for enum
discovery) is a possible earlier source stop; no enum cache, Java fields or class
initialization states are written to bypass it.

To build a fresh independent candidate while its source pins remain current:

```powershell
D:/Dev/Python312/python.exe -B scripts/stack-walk-candidate.py build `
  --state .boom/runtime-provider-rebases/io-park-tool105-v149-a/pending-state.json `
  --output .boom/stack-walk/source-review-fresh
D:/Dev/Python312/python.exe -B -m unittest tests.stack_walk_class_only -v
```

Successful compilation or the reference oracle does not establish original
callback execution, eight-thread candidate behavior, complete StackWalker,
formal provider acceptance or game startup.

The root independently rebuilt and reassembled a fresh candidate at
`.boom/stack-walk/root-review-source-v155-a/verification.json`, SHA256
`6298500d6f59f6cc0cb6a5bf9423a6258524ea3705f53da491c171ca0c4cad66`.
The eight boundary tests and a fresh1025-call JDK oracle also passed; the latter
receipt is `.boom/stack-walk/root-review-oracle-v155-a/verification.json`, SHA256
`c885982d59600d048afc289920a20ec84438a5cc6e1eb51a3f84cf1251afdd37`.
These checks retain the explicit `callback_execution_verified=false` boundary.
