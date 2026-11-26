param([string]$Output='.boom\assembly-runtime',[string]$WordPlan='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw 'MSVC x64 tools were not found.' }
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'um\x64\kernel32.lib') } | Sort-Object Name -Descending | Select-Object -First 1
if (-not $sdk) { throw 'Windows SDK import libraries were not found.' }
$outputPath=[IO.Path]::GetFullPath($Output)
[IO.Directory]::CreateDirectory($outputPath) | Out-Null
$object=Join-Path $outputPath 'parallel.obj'
$dll=Join-Path $outputPath 'boom-runtime.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" (Join-Path $projectRoot 'native\runtime\parallel.asm')
if ($LASTEXITCODE -ne 0) { throw 'Runtime assembly failed.' }
$poolObject=Join-Path $outputPath 'pool.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$poolObject" (Join-Path $projectRoot 'native\runtime\pool.asm')
if ($LASTEXITCODE -ne 0) { throw 'Persistent pool assembly failed.' }
$heapObject=Join-Path $outputPath 'heap.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$heapObject" (Join-Path $projectRoot 'native\runtime\heap.asm')
if ($LASTEXITCODE -ne 0) { throw 'Heap assembly failed.' }
$rootSpansObject=Join-Path $outputPath 'heap_root_spans.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$rootSpansObject" (Join-Path $projectRoot 'native\runtime\heap_root_spans.asm')
if ($LASTEXITCODE -ne 0) { throw 'Heap root-region assembly failed.' }
$referencePendingObject=Join-Path $outputPath 'reference_pending.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$referencePendingObject" (Join-Path $projectRoot 'native/runtime/reference_pending.asm')
if($LASTEXITCODE -ne 0){throw 'Pending-reference transport assembly failed'}
$monitorAbortObject=Join-Path $outputPath 'monitor_abort.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$monitorAbortObject" (Join-Path $projectRoot 'native/runtime/monitor_abort.asm')
if($LASTEXITCODE -ne 0){throw 'Monitor teardown assembly failed'}
$javaInternObject=Join-Path $outputPath 'java_string_intern.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaInternObject" (Join-Path $projectRoot 'native\runtime\java_string_intern.asm')
if ($LASTEXITCODE -ne 0) { throw 'Source String intern assembly failed.' }
$javaConcatObject=Join-Path $outputPath 'java_concat.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaConcatObject" (Join-Path $projectRoot 'native/runtime/java_concat.asm')
if($LASTEXITCODE -ne 0){throw 'Normal Java concat assembly failed'}
$javaBitcastsObject=Join-Path $outputPath 'java_bitcasts.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaBitcastsObject" (Join-Path $projectRoot 'native/runtime/java_bitcasts.asm')
if($LASTEXITCODE -ne 0){throw 'Normal raw-bit service assembly failed'}
$javaClassLookupObject=Join-Path $outputPath 'java_class_lookup.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaClassLookupObject" (Join-Path $projectRoot 'native/runtime/java_class_lookup.asm')
if ($LASTEXITCODE -ne 0) { throw 'Normal Class lookup assembly failed.' }
$javaCallerObject=Join-Path $outputPath 'java_caller.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaCallerObject" (Join-Path $projectRoot 'native/runtime/java_caller.asm')
if ($LASTEXITCODE -ne 0) { throw 'Normal caller service assembly failed.' }
$stackProbeObject=Join-Path $outputPath 'stack_probe.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$stackProbeObject" (Join-Path $projectRoot 'native/runtime/stack_probe.asm')
if ($LASTEXITCODE -ne 0) { throw 'Generated Java stack probe assembly failed.' }
$javaUnsafeFieldsObject=Join-Path $outputPath 'java_unsafe_fields.obj' 
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaUnsafeFieldsObject" (Join-Path $projectRoot 'native/runtime/java_unsafe_fields.asm')
if($LASTEXITCODE -ne 0){throw 'Normal Unsafe field assembly failed.'}
$javaUnsafeObject=Join-Path $outputPath 'java_unsafe.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaUnsafeObject" (Join-Path $projectRoot 'native/runtime/java_unsafe.asm')
if($LASTEXITCODE -ne 0){throw 'Normal Unsafe bootstrap assembly failed'}
$javaClassBootstrapObject=Join-Path $outputPath 'java_class_bootstrap.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaClassBootstrapObject" (Join-Path $projectRoot 'native/runtime/java_class_bootstrap.asm')
if($LASTEXITCODE -ne 0){throw 'Normal Class bootstrap assembly failed'}
$javaPropertiesObject=Join-Path $outputPath 'java_properties.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaPropertiesObject" (Join-Path $projectRoot 'native\runtime\java_properties.asm')
if ($LASTEXITCODE -ne 0) { throw 'Normal property callbacks assembly failed.' }
$monitorObject=Join-Path $outputPath 'monitors.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$monitorObject" (Join-Path $projectRoot 'native\runtime\monitors.asm')
if ($LASTEXITCODE -ne 0) { throw 'Monitor assembly failed.' }
$arrayObject=Join-Path $outputPath 'arrays.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$arrayObject" (Join-Path $projectRoot 'native\runtime\arrays.asm')
if ($LASTEXITCODE -ne 0) { throw 'Array assembly failed.' }
$objectRuntime=Join-Path $outputPath 'objects.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$objectRuntime" (Join-Path $projectRoot 'native\runtime\objects.asm')
if ($LASTEXITCODE -ne 0) { throw 'Object assembly failed.' }
$schedulerObject=Join-Path $outputPath 'scheduler.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$schedulerObject" (Join-Path $projectRoot 'native\runtime\scheduler.asm')
if ($LASTEXITCODE -ne 0) { throw 'Scheduler assembly failed.' }
$referenceObject=Join-Path $outputPath 'references.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$referenceObject" (Join-Path $projectRoot 'native\runtime\references.asm')
if ($LASTEXITCODE -ne 0) { throw 'Reference array assembly failed.' }
$classObject=Join-Path $outputPath 'classes.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$classObject" (Join-Path $projectRoot 'native\runtime\classes.asm')
if ($LASTEXITCODE -ne 0) { throw 'Class runtime assembly failed.' }
$class32Object=Join-Path $outputPath 'classes32.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$class32Object" (Join-Path $projectRoot 'native\runtime\classes32.asm')
if ($LASTEXITCODE -ne 0) { throw 'Context32 class runtime assembly failed.' }
$unwindObject=Join-Path $outputPath 'unwind.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$unwindObject" (Join-Path $projectRoot 'native\runtime\unwind.asm')
if ($LASTEXITCODE -ne 0) { throw 'Context32 exception runtime assembly failed.' }
$typeObject=Join-Path $outputPath 'types.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$typeObject" (Join-Path $projectRoot 'native\runtime\types.asm')
if ($LASTEXITCODE -ne 0) { throw 'Type runtime assembly failed.' }
$stringObject=Join-Path $outputPath 'strings.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$stringObject" (Join-Path $projectRoot 'native\runtime\strings.asm')
if ($LASTEXITCODE -ne 0) { throw 'String runtime assembly failed.' }
$unicodeObject=Join-Path $outputPath 'unicode_case.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$unicodeObject" (Join-Path $projectRoot 'native\runtime\unicode_case.asm')
if ($LASTEXITCODE -ne 0) { throw 'Unicode case assembly failed.' }
$mirrorObject=Join-Path $outputPath 'mirrors.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$mirrorObject" (Join-Path $projectRoot 'native\runtime\mirrors.asm')
if($LASTEXITCODE -ne 0){throw 'Class mirror assembly failed.'}
$javaClassObject=Join-Path $outputPath 'java_classes.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$javaClassObject" (Join-Path $projectRoot 'native/runtime/java_classes.asm')
if($LASTEXITCODE -ne 0){throw 'Normal Java Class runtime assembly failed.'}
$dynamicStringObject=Join-Path $outputPath 'string_dynamic.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$dynamicStringObject" (Join-Path $projectRoot 'native\runtime\string_dynamic.asm')
if($LASTEXITCODE -ne 0){throw 'Dynamic String assembly failed.'}
$concatObject=Join-Path $outputPath 'concat.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$concatObject" (Join-Path $projectRoot 'native\runtime\concat.asm')
if($LASTEXITCODE -ne 0){throw 'Concat assembly failed.'}
$runtimeTypeObject=Join-Path $outputPath 'runtime_types.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$runtimeTypeObject" (Join-Path $projectRoot 'native\runtime\runtime_types.asm')
if($LASTEXITCODE -ne 0){throw 'Runtime type assembly failed.'}
$runtimeIndexObject=Join-Path $outputPath 'runtime_type_index.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$runtimeIndexObject" (Join-Path $projectRoot 'native/runtime/runtime_type_index.asm')
if($LASTEXITCODE -ne 0){throw 'Indexed runtime type assembly failed.'}
$fieldAddressObject=Join-Path $outputPath 'field_address.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$fieldAddressObject" (Join-Path $projectRoot 'native/runtime/field_address.asm')
if($LASTEXITCODE -ne 0){throw 'Source field address assembly failed.'}
$covariantObject=Join-Path $outputPath 'covariant_arrays.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$covariantObject" (Join-Path $projectRoot 'native\runtime\covariant_arrays.asm')
if($LASTEXITCODE -ne 0){throw 'Covariant reference array assembly failed.'}
$exceptionObject=Join-Path $outputPath 'exceptions.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$exceptionObject" (Join-Path $projectRoot 'native\runtime\exceptions.asm')
if($LASTEXITCODE -ne 0){throw 'Exception propagation assembly failed.'}
$framesObject=Join-Path $outputPath 'frames.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$framesObject" (Join-Path $projectRoot 'native\runtime\frames.asm')
if($LASTEXITCODE -ne 0){throw 'frames runtime assembly failed.'}
$throwablesObject=Join-Path $outputPath 'throwables.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$throwablesObject" (Join-Path $projectRoot 'native\runtime\throwables.asm')
if($LASTEXITCODE -ne 0){throw 'throwables runtime assembly failed.'}
$streamObject=Join-Path $outputPath 'file_streams.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$streamObject" (Join-Path $projectRoot 'native\runtime\file_streams.asm')
if($LASTEXITCODE -ne 0){throw 'Stream field runtime assembly failed.'}
$fdObject=Join-Path $outputPath 'file_descriptors.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$fdObject" (Join-Path $projectRoot 'native\runtime\file_descriptors.asm')
if($LASTEXITCODE -ne 0){throw 'FileDescriptor runtime assembly failed.'}
$cdsObject=Join-Path $outputPath 'cds.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$cdsObject" (Join-Path $projectRoot 'native\runtime\cds.asm')
if($LASTEXITCODE -ne 0){throw 'CDS runtime assembly failed.'}
$stringJoinObject=Join-Path $outputPath 'string_join.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$stringJoinObject" (Join-Path $projectRoot 'native\runtime\string_join.asm')
if($LASTEXITCODE -ne 0){throw 'String join runtime assembly failed.'}
$reflectedFieldsObject=Join-Path $outputPath 'reflect_fields.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$reflectedFieldsObject" (Join-Path $projectRoot 'native/runtime/reflect_fields.asm')
if($LASTEXITCODE -ne 0){throw 'Reflected Field runtime assembly failed.'}
$inetAddressObject=Join-Path $outputPath 'inet_address.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$inetAddressObject" (Join-Path $projectRoot 'native/runtime/inet_address.asm')
if($LASTEXITCODE -ne 0){throw 'InetAddress metadata cache assembly failed.'}
$sequenceReplaceObject=Join-Path $outputPath 'string_sequence_replace.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$sequenceReplaceObject" (Join-Path $projectRoot 'native/runtime/string_sequence_replace.asm')
if($LASTEXITCODE -ne 0){throw 'String sequence replacement assembly failed.'}

$systemObject=Join-Path $outputPath 'system.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$systemObject" (Join-Path $projectRoot 'native\runtime\system.asm')
if($LASTEXITCODE -ne 0){throw 'System runtime assembly failed.'}
$resourceObject=Join-Path $outputPath 'resources.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$resourceObject" (Join-Path $projectRoot 'native\runtime\resources.asm')
if($LASTEXITCODE -ne 0){throw 'Resource assembly failed.'}
$layerObject=Join-Path $outputPath 'layers.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$layerObject" (Join-Path $projectRoot 'native\runtime\layers.asm')
if($LASTEXITCODE -ne 0){throw 'Module layer assembly failed.'}
$wordPlanObject=@()
$wordPlanExports=@()
if($WordPlan){
    $wordPlanObject=@((Join-Path $outputPath 'word-plan.obj'))
    & (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$($wordPlanObject[0])" ([IO.Path]::GetFullPath($WordPlan))
    if($LASTEXITCODE -ne 0){throw 'Word plan assembly failed.'}
    $wordPlanExports=@('/EXPORT:boom_get_word_plan')
}
$lowercaseObject=Join-Path $outputPath 'string_lowercase.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$lowercaseObject" (Join-Path $projectRoot 'native\runtime\string_lowercase.asm')
if($LASTEXITCODE -ne 0){throw 'Locale lowercase assembly failed.'}
$wordBreakObject=Join-Path $outputPath 'word_break.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$wordBreakObject" (Join-Path $projectRoot 'native\runtime\word_break.asm')
if($LASTEXITCODE -ne 0){throw 'Word boundary assembly failed.'}
$unicodeContextObject=Join-Path $outputPath 'unicode_context.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$unicodeContextObject" (Join-Path $projectRoot 'native\runtime\unicode_context.asm')
if($LASTEXITCODE -ne 0){throw 'Unicode context assembly failed.'}
$stringConstructionObject=Join-Path $outputPath 'string_construction.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$stringConstructionObject" (Join-Path $projectRoot 'native\runtime\string_construction.asm')
if ($LASTEXITCODE -ne 0) { throw 'String construction assembly failed.' }
$moduleObjectsObject=Join-Path $outputPath 'module_objects.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$moduleObjectsObject" (Join-Path $projectRoot 'native\runtime\module_objects.asm')
if ($LASTEXITCODE -ne 0) { throw 'Physical Module assembly failed.' }
$moduleObject=Join-Path $outputPath 'modules.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$moduleObject" (Join-Path $projectRoot 'native\runtime\modules.asm')
if($LASTEXITCODE -ne 0){throw 'Module identity assembly failed.'}
$clockObject=Join-Path $outputPath 'vm_clock.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$clockObject" (Join-Path $projectRoot 'native\runtime\vm_clock.asm')
if($LASTEXITCODE -ne 0){throw 'VM clock assembly failed.'}
$propertiesObject=Join-Path $outputPath 'system_properties.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$propertiesObject" (Join-Path $projectRoot 'native\runtime\system_properties.asm')
if ($LASTEXITCODE -ne 0) { throw 'System properties assembly failed.' }
$concatApiObject=Join-Path $outputPath 'string_concat_api.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$concatApiObject" (Join-Path $projectRoot 'native\runtime\string_concat_api.asm')
if ($LASTEXITCODE -ne 0) { throw 'String.concat assembly failed.' }
$identityObject=Join-Path $outputPath 'identity_hash.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$identityObject" (Join-Path $projectRoot 'native\runtime\identity_hash.asm')
if ($LASTEXITCODE -ne 0) { throw 'Identity hash assembly failed.' }
$hexObject=Join-Path $outputPath 'hex_strings.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$hexObject" (Join-Path $projectRoot 'native\runtime\hex_strings.asm')
if ($LASTEXITCODE -ne 0) { throw 'Hex string assembly failed.' }
$snapshotObject=Join-Path $outputPath 'builder_snapshot.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$snapshotObject" (Join-Path $projectRoot 'native\runtime\builder_snapshot.asm')
if ($LASTEXITCODE -ne 0) { throw 'Builder snapshot assembly failed.' }
$vmPropertiesObject=Join-Path $outputPath 'vm_properties.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$vmPropertiesObject" (Join-Path $projectRoot 'native\runtime\vm_properties.asm')
if ($LASTEXITCODE -ne 0) { throw 'VM properties assembly failed.' }
$classQueryObject=Join-Path $outputPath 'class_queries.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$classQueryObject" (Join-Path $projectRoot 'native\runtime\class_queries.asm')
if ($LASTEXITCODE -ne 0) { throw 'Class queries assembly failed.' }
$replaceObject=Join-Path $outputPath 'string_replace.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$replaceObject" (Join-Path $projectRoot 'native\runtime\string_replace.asm')
if ($LASTEXITCODE -ne 0) { throw 'String replacement assembly failed.' }
$cloneObject=Join-Path $outputPath 'array_clone.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$cloneObject" (Join-Path $projectRoot 'native\runtime\array_clone.asm')
if ($LASTEXITCODE -ne 0) { throw 'Array clone assembly failed.' }
$vmRegistrationObject=Join-Path $outputPath 'vm_registration.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$vmRegistrationObject" (Join-Path $projectRoot 'native\runtime\vm_registration.asm')
if ($LASTEXITCODE -ne 0) { throw 'VM registration assembly failed.' }
$threadNativesObject=Join-Path $outputPath 'thread_natives.obj'
$unsafeObject=Join-Path $outputPath 'unsafe_bootstrap.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$unsafeObject" (Join-Path $projectRoot 'native\runtime\unsafe_bootstrap.asm')
if($LASTEXITCODE -ne 0){throw 'Unsafe bootstrap assembly failed.'}
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$threadNativesObject" (Join-Path $projectRoot 'native\runtime\thread_natives.asm')
if($LASTEXITCODE -ne 0){throw 'Thread native assembly failed.'}
$scopedMemoryObject=Join-Path $outputPath 'scoped_memory.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$scopedMemoryObject" (Join-Path $projectRoot 'native\runtime\scoped_memory.asm')
if($LASTEXITCODE -ne 0){throw 'Scoped memory assembly failed.'}
$winfsObject=Join-Path $outputPath 'winnt_file_system.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$winfsObject" (Join-Path $projectRoot 'native\runtime\winnt_file_system.asm')
if($LASTEXITCODE -ne 0){throw 'Windows file system assembly failed.'}
$reflectionArraysObject=Join-Path $outputPath 'reflection_arrays.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$reflectionArraysObject" (Join-Path $projectRoot 'native\runtime\reflection_arrays.asm')
if($LASTEXITCODE -ne 0){throw 'Reflection array assembly failed.'}
$classLoadersObject=Join-Path $outputPath 'class_loaders.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$classLoadersObject" (Join-Path $projectRoot 'native\runtime\class_loaders.asm')
if($LASTEXITCODE -ne 0){throw 'Class loader VM field assembly failed.'}
$windowsStartupObject=Join-Path $outputPath 'windows_startup.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$windowsStartupObject" (Join-Path $projectRoot 'native\runtime\windows_startup.asm')
if($LASTEXITCODE -ne 0){throw 'Windows startup assembly failed.'}
$signalNativeObject=Join-Path $outputPath 'signal_natives.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$signalNativeObject" (Join-Path $projectRoot 'native\runtime\signal_natives.asm')
if($LASTEXITCODE -ne 0){throw 'Signal native binding assembly failed.'}
$accessObject=Join-Path $outputPath 'access_context.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$accessObject" (Join-Path $projectRoot 'native\runtime\access_context.asm')
if($LASTEXITCODE -ne 0){throw 'Access context assembly failed.'}
$threadRegistryObject=Join-Path $outputPath 'thread_registry.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$threadRegistryObject" (Join-Path $projectRoot 'native\runtime\thread_registry.asm')
if($LASTEXITCODE -ne 0){throw 'Thread registry assembly failed.'}
$signalControlObject=Join-Path $outputPath 'signal_control.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$signalControlObject" (Join-Path $projectRoot 'native\runtime\signal_control.asm')
if($LASTEXITCODE -ne 0){throw 'Signal control assembly failed.'}
$signalObject=Join-Path $outputPath 'signals.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$signalObject" (Join-Path $projectRoot 'native\runtime\signals.asm')
if($LASTEXITCODE -ne 0){throw 'Signal lookup assembly failed.'}
$prefixObject=Join-Path $outputPath 'string_prefix.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$prefixObject" (Join-Path $projectRoot 'native\runtime\string_prefix.asm')
if($LASTEXITCODE -ne 0){throw 'String prefix runtime assembly failed.'}
$systemStreamObject=Join-Path $outputPath 'system_streams.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$systemStreamObject" (Join-Path $projectRoot 'native\runtime\system_streams.asm')
if($LASTEXITCODE -ne 0){throw 'System stream setter assembly failed.'}
$charsObject=Join-Path $outputPath 'string_chars.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$charsObject" (Join-Path $projectRoot 'native\runtime\string_chars.asm')
if($LASTEXITCODE -ne 0){throw 'String character copy runtime assembly failed.'}
$classForNameObject=Join-Path $outputPath 'class_for_name.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$classForNameObject" (Join-Path $projectRoot 'native\runtime\class_for_name.asm')
if($LASTEXITCODE -ne 0){throw 'Class name lookup assembly failed.'}
$reflectNewObject=Join-Path $outputPath 'reflect_new.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$reflectNewObject" (Join-Path $projectRoot 'native\runtime\reflect_new.asm')
if($LASTEXITCODE -ne 0){throw 'Reflective constructor assembly failed.'}
$splitObject=Join-Path $outputPath 'string_split.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$splitObject" (Join-Path $projectRoot 'native\runtime\string_split.asm')
if($LASTEXITCODE -ne 0){throw 'String split assembly failed.'}
$typedArrayObject=Join-Path $outputPath 'typed_arrays.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$typedArrayObject" (Join-Path $projectRoot 'native\runtime\typed_arrays.asm')
if ($LASTEXITCODE -ne 0) { throw 'Typed arrays assembly failed.' }
$runtimeProcessorsObject=Join-Path $outputPath 'runtime_resources.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$runtimeProcessorsObject" (Join-Path $projectRoot 'native/runtime/runtime_resources.asm')
if($LASTEXITCODE -ne 0){throw 'Runtime processor service assembly failed'}
$reflectedConstructorsObject=Join-Path $outputPath 'reflect_constructors.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$reflectedConstructorsObject" (Join-Path $projectRoot 'native/runtime/reflect_constructors.asm')
if($LASTEXITCODE -ne 0){throw 'Reflective constructors assembly failed'}
$shutdownObject=Join-Path $outputPath 'shutdown.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$shutdownObject" (Join-Path $projectRoot 'native/runtime/shutdown.asm')
if($LASTEXITCODE -ne 0){throw 'Shutdown service assembly failed'}
$vmThreadBootstrapObject=Join-Path $outputPath 'vm_thread_bootstrap.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$vmThreadBootstrapObject" (Join-Path $projectRoot 'native/runtime/vm_thread_bootstrap.asm')
if($LASTEXITCODE -ne 0){throw 'Normal VM thread bootstrap assembly failed'}
# Native registration compares actual DLL entry addresses, so expose every table slot.
$threadNativeExports=@(0..17 | ForEach-Object { '/EXPORT:boom_thread_native_'+$_ })
$threadNativeExports+='/EXPORT:boom_threads_set_priority'
$referencePendingExports=@('create','publish','get','has','wait','stop','stopping','roots_begin','roots_end','destroy')|ForEach-Object{'/EXPORT:boom_reference_pending_'+$_}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_scoped_native_register /EXPORT:boom_scoped_close_unavailable /EXPORT:boom_winfs_init /EXPORT:boom_reflect_array_allocate /EXPORT:boom_class_loader_field /EXPORT:boom_class_loader_bind /EXPORT:boom_class_loader_register /EXPORT:boom_class_loader_retrieve /EXPORT:boom_windows_error_mode /EXPORT:boom_signal_native_query /EXPORT:boom_signal_native_bind /EXPORT:boom_access_context_query /EXPORT:boom_access_bind_domain /EXPORT:boom_unsafe_native /EXPORT:boom_unsafe_constants_fill /EXPORT:boom_trace_enter /EXPORT:boom_trace_leave /EXPORT:boom_trace_release /EXPORT:boom_trace_head /EXPORT:boom_throwable_fill /EXPORT:boom_stream_fields_init /EXPORT:boom_stream_descriptor /EXPORT:boom_fd_service /EXPORT:boom_cds_service /EXPORT:boom_layer_intrinsic /EXPORT:boom_field_service /EXPORT:boom_field_virtual /EXPORT:boom_field_static_address /EXPORT:boom_field_instance_address /EXPORT:boom_constructor_service /EXPORT:boom_constructor_virtual /EXPORT:boom_processor_count /EXPORT:boom_runtime_available_processors /EXPORT:boom_runtime_resource /EXPORT:boom_class_for_name /EXPORT:boom_class_find_bootstrap /EXPORT:boom_class_loader_key /EXPORT:boom_heap_contains /EXPORT:boom_reflect_new /EXPORT:boom_exception_create /EXPORT:boom_string_split /EXPORT:boom_string_lowercase /EXPORT:boom_word_is_boundary /EXPORT:boom_word_next /EXPORT:boom_unicode_context /EXPORT:boom_string_new /EXPORT:boom_string_construct_chars /EXPORT:boom_string_construct_chars_all /EXPORT:boom_boot_unnamed_publish /EXPORT:boom_module_objects_value /EXPORT:boom_module_pool_valid /EXPORT:boom_module_index /EXPORT:boom_module_load /EXPORT:boom_module_intrinsic /EXPORT:boom_string_join /EXPORT:boom_string_replace_sequence /EXPORT:boom_platform_properties /EXPORT:boom_java_concat /EXPORT:boom_java_class_bootstrap /EXPORT:boom_java_caller /EXPORT:boom_java_caller_type /EXPORT:boom_stack_probe /EXPORT:boom_java_class_lookup /EXPORT:boom_java_bitcast /EXPORT:boom_java_unsafe /EXPORT:boom_java_unsafe_field /EXPORT:boom_java_unsafe_field_address /EXPORT:boom_java_unsafe_memory /EXPORT:boom_java_unsafe_constants /EXPORT:boom_java_property_array /EXPORT:boom_java_property_copy /EXPORT:boom_java_property_literal /EXPORT:boom_string_concat_api /EXPORT:boom_identity_hash /EXPORT:boom_hex_string /EXPORT:boom_builder_snapshot /EXPORT:boom_vm_properties /EXPORT:boom_class_is_hidden /EXPORT:boom_class_name /EXPORT:boom_class_value_field /EXPORT:boom_shutdown_native /EXPORT:boom_string_replace /EXPORT:boom_string_replace_literal_chars /EXPORT:boom_string_to_chars /EXPORT:boom_string_starts_with /EXPORT:boom_signal_find $threadNativeExports $referencePendingExports /EXPORT:boom_monitor_abort_owned /EXPORT:boom_thread_native_register /EXPORT:boom_thread_native_dispatch /EXPORT:boom_thread_native_bind /EXPORT:boom_vm_thread_bootstrap /EXPORT:boom_threads_create /EXPORT:boom_threads_destroy /EXPORT:boom_threads_next_id /EXPORT:boom_threads_id_address /EXPORT:boom_threads_id_memory /EXPORT:boom_threads_attach /EXPORT:boom_threads_detach /EXPORT:boom_threads_current /EXPORT:boom_threads_start /EXPORT:boom_threads_join /EXPORT:boom_threads_result /EXPORT:boom_threads_release /EXPORT:boom_threads_roots /EXPORT:boom_threads_roots_end /EXPORT:boom_signal_control_create /EXPORT:boom_signal_control_close /EXPORT:boom_signal_control_register /EXPORT:boom_signal_control_raise /EXPORT:boom_signal_control_snapshot /EXPORT:boom_signal_control_thread_slots /EXPORT:boom_signal_control_console /EXPORT:boom_system_stream_set /EXPORT:boom_array_clone /EXPORT:boom_vm_native /EXPORT:boom_finalization_enabled /EXPORT:boom_inet_address_init /EXPORT:boom_inet_address_available /EXPORT:boom_typed_multi_new /EXPORT:boom_typed_array_length /EXPORT:boom_vm_adjustment_from_filetime /EXPORT:boom_system_register /EXPORT:boom_system_dispatch /EXPORT:boom_system_arraycopy /EXPORT:boom_resource_bytes /EXPORT:boom_mirror_primitive /EXPORT:boom_mirror_typeid /EXPORT:boom_vm_current_time_millis /EXPORT:boom_vm_nano_time /EXPORT:boom_vm_filetime_to_millis /EXPORT:boom_vm_counter_to_nanos /EXPORT:boom_class_ensure32 /EXPORT:boom_exception_prepare /EXPORT:boom_exception_materialize /EXPORT:boom_exception_init_failure /EXPORT:boom_exception_class_failed /EXPORT:boom_exception_npe_message /EXPORT:boom_exception_set32 /EXPORT:boom_exception_match32 /EXPORT:boom_exception_take32 /EXPORT:boom_covariant_array /EXPORT:boom_runtime_type /EXPORT:boom_runtime_row /EXPORT:boom_runtime_index_prepare /EXPORT:boom_field_address /EXPORT:boom_runtime_cast /EXPORT:boom_runtime_instanceof /EXPORT:boom_runtime_getclass /EXPORT:boom_java_class_load /EXPORT:boom_java_class_typeid /EXPORT:boom_java_class_bind_loader /EXPORT:boom_java_class_bind_module /EXPORT:boom_java_class_seal /EXPORT:boom_java_class_query /EXPORT:boom_java_class_name /EXPORT:boom_java_string_intern /EXPORT:boom_class_is_instance /EXPORT:boom_mirror_load /EXPORT:boom_mirror_intrinsic /EXPORT:boom_string_concat /EXPORT:boom_string_allocate /EXPORT:boom_string_intern /EXPORT:boom_string_load /EXPORT:boom_unicode_case /EXPORT:boom_unicode_equals_ci /EXPORT:boom_string_intrinsic /EXPORT:boom_string_get_chars /EXPORT:boom_type_assignable /EXPORT:boom_parallel_i32 /EXPORT:boom_class_ensure /EXPORT:boom_parallel_numeric /EXPORT:boom_pool_create /EXPORT:boom_pool_run /EXPORT:boom_pool_run_budget /EXPORT:boom_scheduler_create /EXPORT:boom_scheduler_run /EXPORT:boom_scheduler_budget /EXPORT:boom_scheduler_reset /EXPORT:boom_scheduler_destroy /EXPORT:boom_pool_destroy /EXPORT:boom_monitor_enter /EXPORT:boom_monitor_exit /EXPORT:boom_monitor_notify /EXPORT:boom_monitor_notify_all /EXPORT:boom_heap_create /EXPORT:boom_heap_alloc /EXPORT:boom_heap_collect /EXPORT:boom_heap_collect_spans /EXPORT:boom_heap_destroy /EXPORT:boom_array_new /EXPORT:boom_array_length /EXPORT:boom_array_load /EXPORT:boom_array_store /EXPORT:boom_array_copy /EXPORT:boom_object_new /EXPORT:boom_object_check /EXPORT:boom_reference_array_new /EXPORT:boom_reference_array_length /EXPORT:boom_reference_array_load /EXPORT:boom_reference_array_store "/OUT:$dll" $shutdownObject $reflectedFieldsObject $reflectedConstructorsObject $runtimeProcessorsObject $object $poolObject $heapObject $javaConcatObject $javaBitcastsObject $javaUnsafeObject $javaUnsafeFieldsObject $javaClassLookupObject $javaCallerObject $stackProbeObject $javaClassBootstrapObject $javaPropertiesObject $javaInternObject $rootSpansObject $monitorObject $arrayObject $objectRuntime $schedulerObject $referenceObject $classObject $class32Object $unwindObject $typeObject $stringObject $unicodeObject $mirrorObject $javaClassObject $dynamicStringObject $concatObject $runtimeTypeObject $runtimeIndexObject $fieldAddressObject $covariantObject $exceptionObject $clockObject $propertiesObject $concatApiObject $identityObject $hexObject $snapshotObject $vmPropertiesObject $classQueryObject $replaceObject $accessObject $signalNativeObject $windowsStartupObject $classLoadersObject $reflectionArraysObject $scopedMemoryObject $winfsObject $unsafeObject $threadNativesObject $threadRegistryObject $referencePendingObject $monitorAbortObject $vmThreadBootstrapObject $signalControlObject $signalObject $prefixObject $systemStreamObject $charsObject $cloneObject $vmRegistrationObject $typedArrayObject $moduleObject $moduleObjectsObject $stringConstructionObject $wordBreakObject $unicodeContextObject $lowercaseObject $classForNameObject $reflectNewObject $splitObject $wordPlanObject $wordPlanExports $layerObject $resourceObject $systemObject $stringJoinObject $sequenceReplaceObject $inetAddressObject $cdsObject $fdObject $streamObject $framesObject $throwablesObject (Join-Path $sdk.FullName 'um\x64\kernel32.lib') (Join-Path $sdk.FullName 'um\x64\synchronization.lib') (Join-Path $sdk.FullName 'um\x64\bcrypt.lib') (Join-Path $sdk.FullName 'um\x64\advapi32.lib') (Join-Path $sdk.FullName 'um\x64\shell32.lib') (Join-Path $sdk.FullName 'um\x64\ole32.lib') (Join-Path $sdk.FullName 'um\x64\ntdll.lib') (Join-Path $sdk.FullName 'um\x64\user32.lib') (Join-Path $sdk.FullName 'um\x64\ws2_32.lib')
if ($LASTEXITCODE -ne 0) { throw 'Runtime link failed.' }
$sourceHashes=[ordered]@{}
foreach($name in @('vm_thread_bootstrap.asm','java_caller.asm','stack_probe.asm','shutdown.asm','reflect_fields.asm','inet_address.asm','string_sequence_replace.asm','reflect_constructors.asm','runtime_resources.asm','class_for_name.asm','reflect_new.asm','string_split.asm','string_lowercase.asm','word_break.asm','unicode_context.asm','string_construction.asm','module_objects.asm','scoped_memory.asm','winnt_file_system.asm','reflection_arrays.asm','class_loaders.asm','windows_startup.asm','signal_natives.asm','access_context.asm','unsafe_bootstrap.asm','thread_natives.asm','thread_registry.asm','reference_pending.asm','monitor_abort.asm','signal_control.asm','signals.asm','string_prefix.asm','system_streams.asm','string_chars.asm','typed_arrays.asm','vm_registration.asm','array_clone.asm','string_replace.asm','class_queries.asm','vm_properties.asm','builder_snapshot.asm','hex_strings.asm','identity_hash.asm','string_concat_api.asm','system_properties.asm','java_properties.asm','java_concat.asm','java_class_bootstrap.asm','java_unsafe.asm','java_unsafe_fields.asm','java_class_lookup.asm','java_bitcasts.asm','unicode_case.asm','classes32.asm','unwind.asm','frames.asm','throwables.asm','file_streams.asm','file_descriptors.asm','cds.asm','parallel.asm','pool.asm','heap.asm','heap_root_spans.asm','monitors.asm','resources.asm','system.asm','string_join.asm','arrays.asm','objects.asm','scheduler.asm','references.asm','classes.asm','types.asm','strings.asm','mirrors.asm','java_classes.asm','java_string_intern.asm','string_dynamic.asm','concat.asm','runtime_types.asm','runtime_type_index.asm','field_address.asm','covariant_arrays.asm','exceptions.asm','vm_clock.asm','modules.asm','layers.asm')){$sourceHashes["native/runtime/$name"]=(Get-FileHash -LiteralPath (Join-Path $projectRoot "native\runtime\$name") -Algorithm SHA256).Hash.ToLowerInvariant()}
$dataSources=[ordered]@{}
foreach($name in @('native/runtime/unicode_case.json','third_party/unicode/LICENSE.txt')){$dataSources[$name]=(Get-FileHash -LiteralPath (Join-Path $projectRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$receipt=[ordered]@{ implementation_language='x86-64 MASM assembly'; sources=$sourceHashes; data_sources=$dataSources; dll=$dll; sha256=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant(); java_runtime=$false; rust_runtime=$false; c_runtime=$false }
[IO.File]::WriteAllText((Join-Path $outputPath 'runtime.json'),($receipt | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
Write-Output "Built $dll"
