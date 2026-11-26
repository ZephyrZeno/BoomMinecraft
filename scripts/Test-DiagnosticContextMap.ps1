param([string]$OutputDirectory)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $OutputDirectory){$OutputDirectory=Join-Path $project ('.boom/diagnostic-context-map-tests/'+[guid]::NewGuid().ToString('N'))}
$root=[IO.Path]::GetFullPath($OutputDirectory);$allowed=[IO.Path]::GetFullPath((Join-Path $project '.boom/diagnostic-context-map-tests'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $root)){throw 'Use a fresh isolated diagnostic sidecar test directory'}
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText((Join-Path $project '.boom/current-diagnostic-context-map-test.txt'),$root)
$source=Join-Path $project 'native/diagnostic/context_map.asm.inc';$hash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$asm=Join-Path $root 'context-map.asm';[IO.File]::WriteAllText($asm,('option casemap:none' + "`n" + [IO.File]::ReadAllText($source) + "`nEND`n"),[Text.UTF8Encoding]::new($false))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$obj=Join-Path $root 'context-map.obj';$dll=Join-Path $root 'context-map.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$obj" $asm *> (Join-Path $root 'assembler.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $root 'assembler.log') -Tail 16;throw 'Context map assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_diagnostic_context_map_record /EXPORT:boom_diagnostic_context_map_row "/OUT:$dll" $obj *> (Join-Path $root 'link.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $root 'link.log') -Tail 12;throw 'Context map link failed'}
Add-Type -Path (Join-Path $project 'tests/host/DiagnosticContextMapProbe.cs');[BoomDiagnosticContextMapProbe]::Run($dll)
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $hash){throw 'Context map kernel changed during verification'}
$result=[ordered]@{passed=$true;scope='isolated_diagnostic_context_sidecar_kernel_only';kernel_language='assembly';distinct_context_parallel_writes=8192;same_context_CAS_writes=8192;forced_hash_collisions=64;bounded_probe_and_overflow_checked=$true;Context32_bytes_and_VM_plan_pointer_preserved=$true;diagnostic_stop_helper_integrated=$false;original_Java_executed=$false;game_started=$false;world_created=$false;source_sha256=$hash.ToLowerInvariant();host_sha256=(Get-FileHash -LiteralPath (Join-Path $project 'tests/host/DiagnosticContextMapProbe.cs') -Algorithm SHA256).Hash.ToLowerInvariant();script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $project '.boom/latest-diagnostic-context-map-test.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
