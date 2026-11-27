# Reusing one verified original source selection

`scripts/existing-source-selection.py` creates a separate immutable envelope
around an existing current source selection. It preserves the selection
directory, original Java Code, original COFF, provider packs and LINK response.
Additional native code or data are verified and linked separately; they are
never described as part of the earlier complete source verifier result.

```powershell
D:/Dev/Python312/python.exe -B scripts/existing-source-selection.py `
  --state <current-verified-input-state> --selection <original-source-round> `
  --output <fresh-envelope-directory>
D:/Dev/Python312/python.exe -B scripts/existing-source-selection.py `
  --verify <envelope-directory>/source-envelope.json
```

Preparation runs the current complete source verifier and requires its result
to equal the original receipt. It validates the actual object set and exact
LINK inputs, captures files read by that invocation before their first read,
and checks all sealed bytes again before publishing. This includes source
shards and imported Python source, plus explicitly declared tools, objects,
libraries and provider inputs. Newly generated verifier scratch files are
excluded from the input set. The temporary audit hook rejects overwrites of
consumed inputs and remains inactive after that invocation; it is a source
tracking tool, not a Python sandbox.

`verify()` checks this specific sealed chain against the current tool
namespace, actual files, exact provider order, original source proof, COFF set
and LINK response. It does not rerun the complete source selection for each
native overlay, grant Java execution admissions or establish runtime success.
Separate candidate and execution tools must seal their own code, data and
test drivers and preserve their narrower scope.

The first Main envelope is
`.boom/normal-constant-pool/existing-main-source-v170-a/source-envelope.json`,
SHA256 `e512645c50db87a9f422e93e3e38c00e1cd913f5d08662352a794c49136568ec`.
Its real complete verification retained 8,652 classes, 71,771 Java methods,
191 original COFF objects and four libraries. The result equals the original
source proof `ba0cb2612c0a8a285014cb8cad96d0124713ca5471c6c4a673a8f224afb1d676`.
It records 1,564 actual read inputs and 1,576 total sealed files. Root separately
verified that envelope and passed the four nested/flat/SHA1, read-set,
overwrite-rejection and completed-scope tests.

This helper remains outside the production provider tool manifest. It supplies
development evidence for separately tested native candidates; it does not
register them or claim complete Main, game or world startup.
