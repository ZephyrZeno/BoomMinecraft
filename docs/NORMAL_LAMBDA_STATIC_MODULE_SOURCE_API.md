# Cross-source public static Lambda source API

[`normal-lambda-static-module-source.py`](../scripts/normal-lambda-static-module-source.py)
adds a versioned source rule for ordinary public static Java methods in another
original source module. Its API is `site(sources, host_class, constant_index)`;
`generated_class` and `runtime_class_name` reuse the original static Class
generator. Same-source sites delegate to the existing static rule unchanged.

The compiler uses the actual original constant pool, bootstrap, declaration,
annotations and loader metadata. It requires standard `LambdaMetafactory`, a
concrete public static Java implementation, a public implementation Class and
functional interface, original JPMS read/export access, and matching reference
loader identities. Reference parameters and captures retain the existing
adaptation rules. Native, abstract, CallerSensitive, signature-polymorphic,
nonpublic, unknown-loader and inaccessible-module targets remain rejected.
REF7, primitive captures, boxing, alternate metafactories and serialization are
outside this rule. This source API runs during translation, outside game execution.

The implementation is published from candidate SHA256
`59e8b77f94e900bfea56316cbc483e87f0080836891f54c88c92b4a4684a3a1e`.
Only its module documentation and repository-root path change. Every function
and class AST, the complete inverse source, `RULE` and `POLICY` are checked.
The installed API SHA256 is
`231af07d58f2f68a3f42066bd356b397dde23eeec8fed4c4c5e15dbc598c51d3`.
The original static and instance API files and all 117 protected tool identities
remain unchanged. The new policy is explicitly composed with the old policy;
old rejection receipts and old prefix records are not reclassified.

## Verified source and caller coverage

The original `PropertiesUtil$Environment.reload()V` CP119 site at PC67 refers
to `Objects.nonNull(Object)boolean`. Real original Class metadata yields the
same contract as the independently checked current28 source append, SHA256
`76afcbff625a12bc99e7782023c5eac03b64e14412baf446f96d17daa4cd99ea`.
The published API passes that acceptance case, the unchanged same-source CP54
case, and fourteen rejection cases. These include original REF7 sites, an
original CallerSensitive ServiceLoader declaration, nonpublic/static/Code
guards, unknown loaders and altered module read/export metadata. Metadata
fixtures do not replace original runtime inputs.

The publication verification is
`.boom/public-static-api-publication-v483-a/verification.json`, SHA256
`a417c97485707b60369d6c32d3bb7d91a60ebb6c642cd45ac6bf6beaf4e4f886`.
It is a source/API check over a bounded original metadata view; it does not
claim a fresh full source-epoch validation or game execution. The earlier
current28 source append separately performed that source validation and
independent generated-Class bytecode checks.

The 28-Class caller passes actual/canonical assembly, complete COFF equality
and preservation of the previous 27-Class machine prefix. New SAM 530920 casts
the erased argument at generated PC2, performs the original Objects Class
ensure, calls normal original method entry 65268 at PC5, and returns its boolean.
The original Java method body is already selected and supplied; its business
logic is not handwritten in the adapter. Objects has no own `<clinit>` but
does have inherited initialization work. Its ensure is therefore retained.
Both original method entry and body have unique definitions in the actual
parent graph. No new virtual dispatcher is introduced.

The caller proof is
`.boom/normal-lambda-public-static-machine-v482-a/machine-b/verification.json`,
SHA256 `145db780790d3300abca44d81444eae160e3a9eb1a75b6a643e6667bcf454dc2`.
An initial checker incorrectly iterated the instruction generator twice; that
checker failure is retained. A new checker materializes the instruction list
once and verifies the same actual/canonical objects, without reassembling them.

Runtime metadata, consumer integration, complete-image execution and Predicate
runtime behavior require their own results. The latest actual Main observation
still stops at CP119; Main initialization, its body, help output, the client
and world creation remain unfinished.
