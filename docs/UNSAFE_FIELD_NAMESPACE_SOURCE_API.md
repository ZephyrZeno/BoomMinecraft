# UFMP namespace source projection

The source library derives all four namespace dimensions from an explicit
UFMP2 pool declaration: type capacity at byte 8, field count at 12, UTF16 name
units at 88 and page count at 92. It validates the 128-byte scalar declaration,
ABI and Field64 record size, and checks the field/page relation. It does not
infer a dimension from an image name, previous epoch, consumer value or field ID.

`derive(pool_source)` returns the dimensions and their actual source positions.
`audit(pool_source, consumers)` accepts a role-to-source mapping. Each detected
local `*_UFMP_` prefix must declare TYPES, FIELDS, NAME_UNITS and PAGES. The audit
identifies their direct DWORD pool comparisons and register comparisons, including
field-index limits and UTF16 end bounds. It records the direct pool-address load
that witnesses a guard's base register, tracks simple register copies and clears
volatile witnesses at calls. It reports unsupported definitions and uses instead
of assigning them a guessed meaning.

`project(pool_source, consumers)` requires that recognized source shape. It edits
only stale integer tokens in the four EQU definitions. Existing comments,
whitespace, line endings, literal bases, instructions and all other source bytes
remain. Each plan includes exact original/projected byte positions and tokens;
reversing those edits must reproduce the entire original source. A final source
audit requires all four dimensions and recognized comparisons to agree with the
explicit pool. A matching type capacity alone cannot make the audit pass.

The pure APIs accept UTF8 text or bytes and perform no filesystem operations.
The CLI reads explicit pool and consumer files and writes an audit or projected
source package to a create-new ignored directory. It checks the output against
the installed Cargo project before reading input files. There is no repository
root override, assembler, linker, source-selection step or execution mode.

The audit is a source consistency check. Pool-address witnesses are not a
general control-flow dominance proof, and a boundary comparison does not prove
the runtime meaning of its register. Unknown expressions, indirect constant uses
or other guard shapes block projection. Numeric literals support decimal and
the documented hexadecimal forms; normal emitted source remains the reference.

The pool source is a configuration input, not proof that every referenced table
or page has the corresponding physical size. A future pool-header-only example
must remain labelled as such. Full table projection, canonical COFF validation,
machine-immediate delta authorization, actual image integration and behavior
remain independent requirements. This library does not modify Java state,
monitors, cleanup policy, old source receipts or registered provider tooling.
