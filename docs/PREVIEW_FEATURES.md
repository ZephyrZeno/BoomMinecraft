# PreviewFeatures startup option query

The assembly runtime implements the original
`jdk.internal.misc.PreviewFeatures.isPreviewEnabled()` native declaration.
It reads an explicit immutable VM startup option. The default is false;
an independently built enabled configuration returns true. Game arguments
are kept separate from VM options.

The reusable source API is
[`preview-features-source.py`](../scripts/preview-features-source.py).
It derives method identities, native Frame32 and the Java boolean cache from
the original Class, source selection and Frame inputs. `metadata`, `render`
and `project` prepare source; they do not assemble, run Java, select extra
methods or register a provider. An optional existing complete source
verification is bound to its exact selection, separately from source rendering.
The CLI writes only to a new directory inside this project's ignored
`.boom`, `target` or `dist` trees.

The implementation is
[`preview_features.asm.inc`](../native/providers/preview_features.asm.inc),
with its contract in
[`preview-features-abi.json`](../native-config/preview-features-abi.json).
The PRVW16/1 pool contains the magic, ABI, size and configured boolean in
read-only image data. There are no new oop roots or Java layout changes.
The original Java class initializer invokes the native method and publishes
its own private static final cache; the public getter reads that cache.
The service preserves an existing pending Context32 and its opaque VM plan.
A malformed clean call sets kind7 and returns zero.

The original contract was checked against the matching JDK source and
isolated default/enabled JDK reference runs. Native component validation
used separate frozen default and enabled images. Each made 108 original
Java API calls, including genuine class initialization, repeated getters,
four OS threads with original Thread/FLS state and pending Context checks.
All 216 calls and normal resource cleanup passed. Warm queries allocated
no additional guest objects or bytes. The two variants have identical
machine code, symbols, imports and unwind data; only the read-only option
value differs.

Component execution hashes:

- Default: `531c3e224e02e77d3db92b44235a8439d3650e8ddf87e9d2da5996d96ba3f9d6`.
- Enabled: `ab92922075f671a26cec024c404749dac404e182e1b397318d270f1d772d5604`.

The current 262-object original Main image retains its 15 native root spans
and passes complete PE byte comparison against an independent relink.
An actual owned-process run then passed the previous PreviewFeatures stop
and reached the original `Class.getEnclosingMethod0()` native declaration.
It exited86 without timing out, with cleanup flags7, zero held monitor
acquisitions and an unlocked monitor registry. Strict report and resource
checks passed. The execution SHA is
`966846f8dc99bbc78ea26077309966e3fff1b00f2dbd2be8d42262e2a6e3f8c0`.
Main class initialization, Main method execution and help output did not
complete. This observation is not a game startup success.

This service does not implement a VM command-line parser or enable preview
classfile execution. Both existing compiler frontends still reject minor
version 65535 and admit non-preview major versions 45 through 65. A true
query result in the component fixture is not proof of preview bytecode support.
Complete Minecraft Main, client and world startup remain unverified.
