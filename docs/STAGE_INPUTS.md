# Build input checks within one stage

`scripts/stage-inputs.py` provides an offline input-validation API for new build
stages. A stage keeps every declared reference, groups compatible absolute paths,
and reads each unique file once before and once after its work. Repeated
references do not cause repeated full-file reads at the same boundary. The API
is experimental and is not yet wired into the existing startup verifier chain.
It adds no game runtime, launcher controls, or persistent verification cache.

## Contract

`InputStage(references, source_epoch=...)` is a single-use context manager.
References have `path` and `digest={size, sha256[, sha1]}`. Paths are resolved and
case-folded for the Windows build environment. Size/SHA256 conflicts and
conflicting optional SHA1 declarations fail before contents are opened. If any
reference declares SHA1, that digest is actually computed in both streaming
passes. Arbitrary additional digest algorithms are rejected.

`canonical_inputs(source_epoch=...)` returns the canonical list only inside an
open stage. The returned digest has the existing two keys, size and SHA256, and
the first path insertion order is retained. The observation record retains all
original references, their additional metadata, and grouping indexes. It also
records actual opens, hash passes, and bytes read at each boundary.

The closing boundary must succeed before publishing a build result. Failed,
closed, reopened, or different-epoch calls cannot supply cached canonical facts.
`validate_inputs(...)` provides the same two fresh boundaries for an immediate
validation call. Each new invocation reads the files again.

Identity, size, modification time, and available birth time are checked around
each streaming read. On this Windows Python 3.12 host, path `stat` and handle
`fstat` expose different `ctime` meanings; their common fields are compared,
while the handle's own `ctime` is still checked before and after its read.

These are boundary checks, not file locks. They do not prove that a file could
never change and change back between boundaries. The caller owns the source
epoch definition and the work performed inside the stage. The API does not
validate original Java selection, reconstruct COFF graphs, resolve symbols,
verify a link response, or replace an independent executable comparison.

## Validation and limits

The installed API is byte-identical to the reviewed 8,563-byte candidate,
SHA256 `f4f28bd0f6e2be7a377c8a648e8378d11fe8c28eff35a32373ee37c7f9d05a75`.
Eight real small-file cases pass: canonical output against the original
`B.unique`, size/SHA256 conflicts, optional SHA1 conflicts and actual mismatches,
missing inputs, same-size mutation during a stage, and closed/cross-epoch reuse.
The local receipt is
`.boom/stage-input-dedupe-v460-a/cases-b/verification.json`, SHA256
`1fd6cf9a8302eaad93d7c612a588340c528d3761245426adec6bbc2900bf4849`.

A separate actual 47,577,708-byte dispatch COFF has five declarations in the
current graph. Both algorithms return exactly the same canonical input. The
original algorithm makes ten actual hash-function calls, reading 475,777,080
logical bytes; the stage API makes two passes, reading 95,155,416 bytes. Its local
receipt is `.boom/stage-input-dedupe-large-v465-a/case-a/verification.json`, SHA256
`0152c3190fb039a2d25e38e347735ccdb91c85fbbb101befb03920457bdc9212`.
This establishes the reduced reads for that input. The single timing sample
uses a call profiler for the original algorithm and a fixed run order; it does
not establish a whole-build speedup or game performance improvement.

The proposed new build wrapper brackets the existing complete-graph checks with
one stage and defers only two adjacent canonicalizations at its own level.
That wrapper has source-only review; it has not built an executable. Ancestor
verifiers and post-link checks still perform their original reads. Existing
startup tools and their locked source identities remain unchanged. Integrating
or broadening this API requires an explicit new build version and validation of
its actual graph and executable.
