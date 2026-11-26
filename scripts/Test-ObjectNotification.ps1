param([Parameter(Mandatory=$true)][string]$Provider,[Parameter(Mandatory=$true)][string]$RuntimeDirectory)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$providerPath=(Resolve-Path -LiteralPath $Provider).Path;$runtime=(Resolve-Path -LiteralPath $RuntimeDirectory).Path
$m=Get-Content -LiteralPath $providerPath -Raw|ConvertFrom-Json;$proof=Get-Content -LiteralPath (Join-Path ([IO.Path]::GetDirectoryName($providerPath)) 'verification.json') -Raw|ConvertFrom-Json
if($m.family -ne 'normal-object-notification-v1' -or -not $proof.verified -or (Get-FileHash -LiteralPath $providerPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $proof.provider_manifest_sha256){throw 'Object notification source receipt differs'}
$metadata=Get-Content -LiteralPath (Join-Path $runtime 'runtime.json') -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath (Join-Path $runtime 'boom-runtime.dll') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.sha256){throw 'Runtime changed'}
foreach($entry in $m.runtime_kernel_sha256.PSObject.Properties){if($metadata.sources.($entry.Name) -ne $entry.Value -or (Get-FileHash -LiteralPath (Join-Path $project $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value){throw 'Notification runtime kernel changed'}}
foreach($artifact in @($m.assembly,$m.object)){if((Get-FileHash -LiteralPath $artifact.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $artifact.digest.sha256){throw 'Provider artifact changed'}}
$root=Join-Path $project ('.boom/object-notification-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText((Join-Path $project '.boom/current-object-notification-test.txt'),$root)
$classSymbol='boom_class'+$m.owner_source.id
$fixture="option casemap:none`n.data?`nALIGN 8`nPUBLIC boom_heap_ptr`nboom_heap_ptr QWORD ?`nPUBLIC $classSymbol`n$classSymbol BYTE 64 DUP(?)`nEND`n"
[IO.File]::WriteAllText((Join-Path $root 'unused-class-fixture.asm'),$fixture,[Text.UTF8Encoding]::new($false))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$obj=Join-Path $root 'fixture.obj';$dll=Join-Path $root 'notification-kernel-probe.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$obj" (Join-Path $root 'unused-class-fixture.asm') *> (Join-Path $root 'assembler.log')
if($LASTEXITCODE -ne 0){throw 'Notification fixture assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_provider_object_notification_service /EXPORT:boom_provider_object_notification_pool /EXPORT:boom_heap_ptr "/OUT:$dll" $obj $m.object.path (Join-Path $runtime 'boom-runtime.lib') *> (Join-Path $root 'link.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $root 'link.log') -Tail 12;throw 'Notification test link failed'}
Add-Type -Path (Join-Path $project 'tests/host/ObjectNotificationProbe.cs');[BoomObjectNotificationProbe]::Run((Join-Path $runtime 'boom-runtime.dll'),$dll)
$r=[ordered]@{passed=$true;scope='existing_verified_notification_COFF_service_ABI_kernel_only';provider_manifest=$providerPath;provider_object_sha256=$m.object.digest.sha256;runtime_sha256=$metadata.sha256;receiver_kinds=@('raw_VM_object_storage','actual_primitive_array');recursive_monitor_ownership_checked=$true;foreign_OS_thread_rejected=$true;unsupported_wait_metadata_rejected=$true;null_and_pending_error_checked=$true;monitor_and_heap_cleanup_completed=$true;unused_class_descriptor_fixture_not_executed=$true;original_Java_native_wrapper_executed=$false;game_started=$false;world_created=$false;host_sha256=(Get-FileHash -LiteralPath (Join-Path $project 'tests/host/ObjectNotificationProbe.cs') -Algorithm SHA256).Hash.ToLowerInvariant();script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();run_directory=$root}
$json=$r|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $project '.boom/latest-object-notification-test.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
