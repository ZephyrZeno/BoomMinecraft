param([Parameter(Mandatory=$true)][string]$Batch,[string]$Runtime='.boom/assembly-runtime-v87-final')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/batch-array-clone-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-batch-array-clone-probe.py') $Batch --output $root > "$root/prepare.log"
if($LASTEXITCODE -ne 0){throw 'Clone probe preparation failed'}
$closure=Get-Content "$root/closure.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$dll=Join-Path $root 'array-clone.dll'
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'))
$lines+=@($closure.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($closure.exports|ForEach-Object{'/EXPORT:'+$_});[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 15;throw 'Clone adapter module link failed'}
Add-Type -Path (Join-Path $project 'tests/host/BatchArrayCloneProbe.cs')
$c=[BoomBatchArrayCloneProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$closure.object_class)
if($c[0] -ne $closure.sites -or $c[1] -ne $closure.source_array_types){throw 'Clone execution coverage differs'}
$result=[ordered]@{passed=$true;scope='all_generated_array_clone_adapters_on_source_typed_arrays';runtime_language='assembly';batch=$closure.batch;adapter_sites=$c[0];source_array_types=$c[1];payload_bytes_checked=$c[2];nested_source_arrays=$c[3];non_null_reference_cases=$c[4];parallel_clones=$c[5];workers=$c[6];error_checks=$c[7];quiescent_collected_blocks=$c[8];covariant_runtime_type_preserved=$true;shallow_reference_identity_preserved=$true;OOM_checked=$true;Java_constructors_executed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
