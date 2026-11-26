param([Parameter(Mandatory=$true)][string]$Provider,[Parameter(Mandatory=$true)][ValidateSet('server','client')][string]$Side)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/file-bootstrap-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-file-bootstrap-probe.py') --provider $Provider --side $Side --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 16;throw 'File bootstrap source verification failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
function Assert-Inputs {
    foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('File bootstrap input changed: '+$r.path)}}
}
Assert-Inputs
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$v=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$v/bin/Hostx64/x64"
$runtime=Split-Path $m.runtime -Parent
[IO.File]::WriteAllText("$root/file.asm",('option casemap:none'+"`n"+[IO.File]::ReadAllText((Join-Path $project 'native/providers/file_bootstrap.asm.inc'))+"`nEND`n"),[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$root/file.obj" "$root/file.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 12;throw 'File bootstrap kernel assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /BREPRO "/OUT:$root/file.dll" "$root/file.obj" (Join-Path $runtime 'boom-runtime.lib') /EXPORT:boom_provider_file_bootstrap_service > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 12;throw 'File bootstrap kernel link failed'}
Add-Type -Path (Join-Path $project 'tests/host/FileBootstrapProviderProbe.cs')
$values=[BoomFileBootstrapProviderProbe]::Run("$root/source.json","$root/file.dll")
Assert-Inputs
$result=[ordered]@{passed=$true;side=$Side;scope='normal_source_stream_descriptor_field_registration_and_Windows_standard_handle_kernel';registered_tables=$values[0];descriptor_cases=$values[1];error_checks=$values[2];workers=$values[3];parallel_calls=$values[4];
fixture_objects_and_tables=$true;source_native_entries_executed=$false;Java_constructors_or_initializers_executed=$false;file_reads_or_writes_executed=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
