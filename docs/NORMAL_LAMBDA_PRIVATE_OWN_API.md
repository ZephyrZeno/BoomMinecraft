# Same-host private Lambda source and assembly APIs

Three maintained tools cover original same-host private instance implementations:

- [`normal-lambda-private-own-source.py`](../scripts/normal-lambda-private-own-source.py)
  checks original bootstrap, declaration, annotations, loader and lookup-host
  identities, generates Class bytes and derives reference/boolean capture layout.
- [`normal-lambda-private-own-assembly.py`](../scripts/normal-lambda-private-own-assembly.py)
  emits assembly for that checked private-call domain, delegating existing
  public and static plans to their unchanged backends.
- [`verify-normal-lambda-private-source.py`](../scripts/verify-normal-lambda-private-source.py)
  independently checks generated Class instructions and their stack semantics.

These are translation tools. The emitted game execution uses assembly and the
original normally translated Java method entry; it has no JVM fallback.

## Access and capture boundaries

An original own-private REF7 implementation is normalized to REF5 and generated
`invokevirtual` opcode 182, matching the original JDK21 metafactory rule for
that domain. The private target remains exact and cannot be overridden. Its
access context is the actual original lookup host and generated hidden
nestmate relationship. A dollar in a name is not an access proof, and a NestHost
attribute is not fabricated. General super/interface special calls, non-own
private targets, constructors, boxing and primitive argument adaptation remain
outside this rule. Existing prefix eligibility and policy receipts remain owned
by their original append version.

Captures may be references or exact boolean Z values. Declaration and argument
indexes retain their source order. Physical payload layout places all reference
slots in an aligned eight-byte prefix, then the boolean bytes. For the checked
`(Environment,String,Z,List)Consumer` site, the physical payload is:

| Capture argument | Payload offset | Width | Oop slot |
| --- | ---: | ---: | --- |
| Environment | 0 | 8 | yes |
| String | 8 | 8 | yes |
| Z | 24 | 1 | no |
| List | 16 | 8 | yes |

Payload size is 25 bytes and reference count is three. The constructor masks
Z with one and stores one byte; the SAM loads that byte with zero extension.
The factory's argument order is unchanged. Field-map width/reference metadata
follows the actual field layout, so the boolean is never reported as an oop.
Instantiated argument casts precede receiver null checks and original private
method calls; generated Frame/Context PCs match actual Class instructions.

## Current validation

The explicit V4 source append preserves all 28 previous records, IDs and Class
bytes and adds original host CP127 and CP187. A single fresh source-base check
and independent Class verifier pass. The source handoff is
`.boom/normal-lambda-private-append-v485-a/source-a/handoff.json`, SHA256
`46744ace19c7bcf034c0a20920166fd050e2c3f9c780e0ffb6e0f75211e99bd1`.

Both actual/canonical adapter assemblies pass ML64, complete COFF comparison,
preservation of the old 28-Class machine prefix and independent private-call/Z
machine checks. Calls target the normal original method entries 510881/510882;
no implementation body or virtual dispatcher is handwritten into the adapter.
This machine-stage handoff is
`.boom/private-lambda-machine-v486-a/handoff-machine-a.json`, SHA256
`bfb52a0341a896f024b6873abcb1543df8edd815eb11225ce10095b39fb64592`.
Its actual-parent binding remains pending until a genuine independently checked
28-Class whole-image result is available. This stage is not a completed native
graph or a runtime behavior test.

The maintained payloads change only documentation and repository-root location.
Every function/Class source and AST remains identical to the tested candidates.
Replay of all 30 generated Classes and the complete 235,837-byte assembly is
byte-identical to the source used for the machine-stage proof; four additional
Z/reference/order/opcode rejection cases pass. Actual formal-path imports and
all 117 protected tool identities also pass. The formal installation receipt is
`.boom/private-lambda-publication-v488-a/formal-installation-verification.json`,
SHA256 `5b7131cae428e6380862e1e781c6367d52112be8333d45ba90297bee3d0a07e7`.
No temporary coordinator is published.

Full metadata integration, interface dispatch, collection, exceptions,
concurrent execution and original Main execution require separate evidence.
The latest actual Main still stops at CP119. Main initialization, help output,
the client and world creation remain unfinished.
