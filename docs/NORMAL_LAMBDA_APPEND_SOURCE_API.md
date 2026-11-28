# Normal Lambda append source APIs

The two source libraries extend an explicit, verified generated prefix. They
reuse the maintained source rule, generated Class writer and assembly backend.
They do not modify the original Java bodies or the existing normal Lambda tools.

`normal-lambda-append-source.append` receives the original `Sources` object,
prefix, requests, current selected source, explicit provenance and a function
that assigns paths to newly generated Class bytes. Requests may be complete
source contracts or `{host_class, constant}` selectors. The function validates
them with the original `site` rule, preserves every old generated record and
reference, and allocates the new tail after the complete prefix. It returns the
aggregate manifest and Class bytes without writing them. Its file wrapper is
`project`; `assembly` renders the aggregate through the existing backend.

`normal-lambda-runtime-append-source.project_units` receives the original
`Sources` object, prefix, aggregate, current common units, the original dispatch
selection and the actual diagnostic catalogue. These last two inputs are
separate: a later ordinary source epoch can retain the original dispatch tables
while the linked diagnostic row identities remain those of an earlier catalogue.
The API follows no image-history fields to discover either input.

The runtime projection returns ten source plans with exact inverse facts. It
appends TYPE and field pointers, normal runtime rows, canonical Class/name data,
non-array Unsafe scales, original-order UFMP UTF16 names/ranges/Field64 pages,
Class lookup capacity, normal Frames, actual dispatch receiver rows and the
initializer-map tail. Only complete source-identified invokedynamic failure
procedures are removed from the actual diagnostic source. Unrelated ordinary
Class descriptors, initializer entries, roots and all other procedures remain
outside the edits. `render` returns the role-to-text map.

Both CLIs accept explicit paths. The append CLI requires prefix verification,
requests, batch/plan and current selection/full Source verification. The runtime
CLI also requires the current unit graph, original dispatch source/proof and
actual diagnostic catalogue. An optional unit-graph proof must identify that
exact graph and an independently equal complete PE. This historical input proof
does not verify the newly rendered machine code. The unchanged generated-Class
semantics verifier is kept distinct from complete original Source verification.

The CLI finds the installed project through Cargo and maintained source markers.
It checks a fresh output under that project's `.boom`, `target` or `dist` before
reading project inputs or creating files. There is no CLI repository-root
override. The Python APIs can return source and Class bytes in memory without
materializing output. A caller may supply existing, byte-checked Class references
when comparing a projection with a previously frozen expansion.

Reference captures use ordinary heap fields: each field has an original-order
ID, an eight-byte reference slot and a matching UFMP/FMAP entry. The generated
layout has the capture count as its reference prefix. Each factory call allocates
a fresh instance; the SAM reads that instance's fields and calls the unchanged
original helper. Null captures retain the original helper's evaluation and
exception order. No private capture table or fixed captured object is used.

The implementation retains the existing bounded source policy: standard
metafactory, static implementation handles, reference captures and the existing
parameter/result adaptations. It adds no boxing, primitive parameter adaptation,
nonstatic handle lowering, arbitrary class loading or automatic collection.
Generated failure roots, Class/name roots and namespace consumers remain explicit
integration work. Existing other UFMP page objects must remain in the replacement
complement. A source-only output does not establish native execution, collection
reachability, thread isolation, complete reflection support or Minecraft startup.
