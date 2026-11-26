param([string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path;$root=Join-Path $project ('.boom/diagnostic-stop-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe -c 'import importlib.util;from pathlib import Path;import sys;s=importlib.util.spec_from_file_location("d",Path("scripts/diagnostic-closure.py"));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);f=dict(kind="method",symbol="boom_m987654",reason="explicit_test_fixture",binding=None,class_id=1,source_sha256="f"*64,method=dict(id=987654,name="test",descriptor="()V",code_sha256=None,stage="declaration",assembly_emitted=False,assembly_unit=None));m.publish(Path(sys.argv[1]),[f],[])' $root
if($LASTEXITCODE -ne 0){throw 'Diagnostic fixture assembly preparation failed'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$root/stops.obj" "$root/diagnostic-stops.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/assembler.log" -Tail 10;throw 'Diagnostic fixture assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT "/OUT:$root/fixture.dll" "$root/stops.obj" /EXPORT:boom_diagnostic_stop /EXPORT:boom_diagnostic_pool /EXPORT:boom_diagnostic_rows /EXPORT:boom_m987654 > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 10;throw 'Diagnostic fixture link failed'}
Add-Type -Path tests/host/DiagnosticStopProbe.cs
$v=[BoomDiagnosticStopProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $root 'fixture.dll'))
$result=[ordered]@{passed=$true;fixture_only=$true;scope='diagnostic_stop_ABI_pending_errors_catch_bypass_and_failed_class_unbound_pool_safety';error_checks=$v[0];parallel_calls=$v[1];workers=$v[2];game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
