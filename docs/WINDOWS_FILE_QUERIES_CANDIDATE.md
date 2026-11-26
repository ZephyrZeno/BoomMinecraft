# Windows legacy readonly file query candidate

This independent candidate implements seven original `java.io.WinNTFileSystem`
natives from the locked JDK 21.0.13+3 classfiles and Windows C source. It does not
register a provider or rebuild the accepted ASM runtime. Method/class/field IDs,
normal layouts, callbacks and native frames are derived from the verified batch.

| Operation | Original declaration | Behavior |
| --- | --- | --- |
| 0 | `getBooleanAttributes0(File)I` | Legacy exists/regular/directory/hidden flags; reserved device filtering; sharing/access-denied fallback; target reparse and AF_UNIX handling. |
| 1 | `getLastModifiedTime0(File)J` | Device-query access, shared handle, unsigned FILETIME division then epoch subtraction; zero on lookup failure. |
| 2 | `getLength0(File)J` | Raw ordinary attributes or target handle; sharing-only fallback with exact basename case, no reparse point and no unsigned overflow. |
| 3 | `listRoots0()I` | Original static native, direct `GetLogicalDrives` mask. |
| 4 | `getSpace0(File,int)J` | Volume path plus total/free/usable disk counters; zero on Windows lookup failure. |
| 5 | `getNameMax0(String)I` | Nullable volume root; original typed `IOException(String)` with the Windows error message on failure. |
| 6 | `checkAccess0(File,int)Z` | `GetFileAttributesW` and target reparse following; READ/EXECUTE existence and WRITE readonly/directory rules. |

`File.path` uses the original WNFS `initIDs` publication and immutable source
FieldID, then the generated inherited receiver FMAP. It is never read through a
guessed File payload offset. Inputs, the filesystem receiver and returned char
arrays are checked against the actual heap and source layouts. Pending exceptions
are preserved. Null and invalid storage are explicit Context32 faults. Invalid
space selectors are rejected; original public Java only uses selectors 0–2.

The existing `native/runtime/win32_path_attributes.asm` is immutable. The candidate
embeds its instructions and data after removing the assembler envelope and
renaming only its two public functions to `boom_query_path_attributes` and
`boom_query_raw_file_attributes`. Actual original/embedded COFF section bytes,
symbol targets, relocations and unwind records must agree after those two exact
renames. The legacy service implements its own C dispatch rules; it does not use
the NIO aggregate result as legacy Java semantics. This primitive is an explicit
source artifact, not a claimed export of runtime572.

The source model pins the original Java/C inputs, File.path's entire inherited
FMAP domain, source String fields and Java error callbacks. The independent
40-byte service pool references the real heap, published WNFS pool and FMAP. An
independent PROP112/2 factory uses the already selected normal String/properties
module; it creates no additional permanent GC roots. Temporary native allocations
are call-owned and counted, with all normal/error returns releasing them.

## Validation

The final candidate is `.boom/windows-file-queries/source-v146-d/candidate.json`
and its `verification.json`. The final execution output is
`.boom/windows-file-queries/execution-v146-j/execution.json`.

The execution image retains every original formal26 Java instruction, descriptor,
class initializer, GC root and linked COFF. An isolated diagnostic object removes
exactly the seven original category-2 native stops; the source stop table and all
other definitions/imports stay intact. The original source verification and real
owned native process receipt, all original COFF/SDK inputs, remaining-stop source
and COFF, candidate and complete canonical LINK response are sealed. The new DLL
adds only the candidate object. It does not claim a fresh formal selection proof
for the extra candidate image.

The component executes original `Properties` constructors/setters and
`System.setProperties`, original File initialization/DefaultFileSystem creation,
original `File(String)` and `String(char[])`, and the seven framed natives.
Positive receivers come from the actual original `File.FS` publication. There are
no host writes to class initialization state, File fields or filesystem fields.

Actual checks include 121 locked-JDK comparisons, 12 additional sharing cases,
all three capacity counters, directory/hidden/readonly/missing/device paths,
embedded NUL, invalid characters, Unicode, absolute/relative long paths, a real
junction, a real AF_UNIX socket and pre-1970 FILETIME. The sharing test distinguishes
case-sensitive length fallback from boolean-attribute lookup. Name-max Windows
failures use original typed IOException construction and message comparison.
Eight OS threads make 1,280 calls; these are development test threads, not a claim
of Java `Thread.start`. Null/wrong storage, pending exceptions, native buffer zero,
unchanged process handle counts and heap destruction are checked.

Free/usable capacity is a live system counter. Total capacity must match exactly;
free/usable readings allow a recorded 16 MiB difference from the separate JDK
process and 64 KiB from the immediate SDK observation. These tolerances do not
apply to any other result. On the recorded final run, the SDK readings and candidate
readings were equal.

The API fixture deliberately does not execute System Phase1. Original
`File.exists()` therefore retains the previously observed
`Blocker.<clinit>` InternalError at PC 37, because original SharedSecrets has not
published JavaLangAccess. The result records this boundary and does not claim the
complete public File.exists chain. An actual owned VM prefix after real Phase1
must prove that chain separately. No JLA slot or class state is patched.

The fixed process cwd used by these tests is part of the path-conversion scope.
The candidate does not claim every CRT allocation-failure site, historical cached
cwd behavior under external `chdir`, automatic/concurrent GC, every possible
Windows filesystem/ACL/reparse type, a complete legacy filesystem implementation,
formal provider acceptance or game startup. Earlier failed runs remain in their
original directories; recheck manifests identify the identical sealed image and
pin the newer execution harness explicitly.

The primary agent independently rebuilt the frozen candidate and replayed the
complete component in two fresh directories. Source verification is
`.boom/windows-file-queries/root-review-source-v147-a/verification.json`, SHA256
`a1f69c11748b64ec10c05e376c80fc0b24cc013903c9548f9767d04233d9fc83`.
Execution is
`.boom/windows-file-queries/root-review-execution-v147-a/execution.json`, SHA256
`ff3a83b026a27b9b22238da041e00cdbd59b54177a4b4ebfa41c389b94a72a80`.
All component checks passed, including 1,280 calls from eight distinct OS
threads, handles 181 before and after, zero native buffers, and heap destruction.
The immediate SDK capacity readings matched exactly. The original public
`File.exists` Blocker boundary remains explicitly recorded.

## Commands

```powershell
python scripts/windows-file-queries-candidate.py `
  --state .boom/accepted-native-three-families-v146-26.json `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/windows-file-queries/source-fresh

python scripts/test-windows-file-queries.py `
  --candidate .boom/windows-file-queries/source-fresh/candidate.json `
  --selection .boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000 `
  --native-manifest .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/vm-entry.json `
  --native-execution .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/execution.json `
  --output .boom/windows-file-queries/execution-fresh
```

Use fresh project output directories. `--recheck-images` creates a new execution
manifest over an unchanged sealed image and records the prior manifest/harness;
it never changes the original proof or native binary.
