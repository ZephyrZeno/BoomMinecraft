# Additional original source dependencies

The development VM preparation command accepts repeated `--source-class
loader:class` and `--source-entry loader:class:method:descriptor` arguments.
These request original source selection before the native entry is built.
They neither provide native implementations nor count as executed Java
admissions. The launcher continues to expose only game launch.

This is needed when a new native implementation constructs an original Java
object whose class descriptor, initializer or Java methods were absent from
the previous selected closure. Linking the native object alone cannot supply
those original Java dependencies.

```powershell
D:\Dev\Python312\python.exe -B scripts/prepare-normal-vm-thread-bootstrap.py `
  --batch <verified-batch> --plan <original-plan> `
  --runtime <assembly-runtime-dll> --output <fresh-round> `
  --profile <source-profile> --server-help `
  --source-class 'bootstrap:jdk/internal/reflect/ConstantPool' `
  --source-entry 'bootstrap:jdk/internal/reflect/ConstantPool:<init>:()V'
```

Supply the existing provider packs and the remaining source dependencies for
the requested path. Run `Build-DiagnosticClosure.ps1 -PreparedSelection` to
assemble and independently verify the resulting selection before building its
VM entry. The options preserve all primordial prerequisites in their original
order, retain loader identity and complete descriptors, and remove duplicate
requests. Invalid root shapes fail before selection. The configuration records
the additional requests with
`additional_source_roots_counted_as_execution=false`.

The actual `v161-main-cp-source-a/round-000` run selected six additional classes
and 34 Java method roots: the original ConstantPool and Tag Java APIs and
initializers, StackWalker.Option, and the required original exception
constructors. It independently verified 8,652 classes and 71,771 original Java
methods, including the real ConstantPool class descriptor and initializer.
`selection-verification.json` has SHA256
`ba0cb2612c0a8a285014cb8cad96d0124713ca5471c6c4a673a8f224afb1d676`.
This remains an incomplete diagnostic source closure with explicit fail stops.

The standard native31 entry built from that selection also passed its actual
native verification and ran the original System phases 1, 2 and 3 to VM level 4.
It passed ASM argv `['--help']` to the original Main initialization request,
stopped at the unprovided `Class.getDeclaredMethods0`, reaped both background
workers and completed heap, registry and Java-frame cleanup. Its execution
receipt is `.boom/vm-entry-images/v161-main-cp-original31-a/execution.json`,
SHA256 `f66c26295418686618830e558811ea74b1d3fc275ad0367ea717be1a1a6d8850`.
Main's body was not called; help, full game startup and world creation were not
completed. The extra source roots are not presented as successful execution of
the ConstantPool API or registration of its candidate provider.

Four source-root contract tests and 14 original Main/argv/ML64 contract tests
passed. Full Python regression at this source revision passed 615 tests with
11 explicit skips. No source Java Code, initializer, logger branch or class
state was substituted to obtain these results.
