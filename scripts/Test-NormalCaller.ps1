param([string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/caller-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$root/probe.obj" (Join-Path $project 'native/diagnostic/stack_probe_fixture.asm') > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 15;throw 'Stack fixture assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT "/OUT:$root/probe.dll" "$root/probe.obj" (Join-Path $runtimePath 'boom-runtime.lib') /EXPORT:boom_test_large_stack > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 15;throw 'Stack fixture link failed'}
Add-Type -Path (Join-Path $project 'tests/host/NormalCallerProbe.cs')
$v=[BoomNormalCallerProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $root 'probe.dll'))
$result=[ordered]@{passed=$true;scope='explicit_TLS_metadata_ABI3_caller_security_flags_context_boundary_pending_error_ABI2_and_actual_64KiB_stack_growth_fixture';error_and_lifecycle_checks=$v[0];parallel_calls=$v[1];workers=$v[2];large_stack_calls=$v[3];source_Java_executed=$false;Class_objects_created=$false;stack_roots=$false;automatic_gc=$false;game_started=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
