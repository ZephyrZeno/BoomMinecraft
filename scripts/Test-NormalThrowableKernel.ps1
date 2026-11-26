param([ValidateSet('server','client')][string]$Side='server')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$status=Get-Content -LiteralPath (Join-Path $project '.boom/current-development-status.json') -Raw|ConvertFrom-Json
$pipeline=Get-Content -LiteralPath (Join-Path $project ('.boom/pending-'+$Side+'-pipeline-v85.json')) -Raw|ConvertFrom-Json
$accepted=$status.diagnostic_startup.System_phase1.$Side.image;$image=$accepted.path
if((Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $accepted.digest.sha256){throw 'Accepted normal source image changed'}
$runtime=Join-Path $status.runtime_directory 'boom-runtime.dll'
if((Get-FileHash -LiteralPath $runtime -Algorithm SHA256).Hash.ToLowerInvariant() -ne $status.runtime_sha256){throw 'Accepted assembly runtime changed'}
$root=Join-Path $project ('.boom/normal-throwable-kernel-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$kernel=Join-Path $project 'native/providers/normal_throwable.asm.inc';$kernelHash=(Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant()
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'normal-throwable-source.py') --batch $status.full_batch.$Side.batch --plan $pipeline.plan --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 14;throw 'Normal Throwable source layout verification failed'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$v=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$v/bin/Hostx64/x64"
[IO.File]::WriteAllText("$root/throwable.asm",('option casemap:none'+"`n"+[IO.File]::ReadAllText($kernel)+"`nEND`n"),[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$root/throwable.obj" "$root/throwable.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 14;throw 'Normal Throwable kernel assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /BREPRO "/OUT:$root/throwable.dll" "$root/throwable.obj" (Join-Path $status.runtime_directory 'boom-runtime.lib') /EXPORT:boom_normal_throwable_fill > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 14;throw 'Normal Throwable kernel link failed'}
Add-Type -Path (Join-Path $project 'tests/host/NormalThrowableKernelProbe.cs')
$values=[BoomNormalThrowableKernelProbe]::Run($runtime,$image,"$root/throwable.dll","$root/source.json")
if((Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $kernelHash -or (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $accepted.digest.sha256){throw 'Normal Throwable accepted input changed during execution'}
$r=[ordered]@{passed=$true;side=$Side;scope='normal_source_Throwable_layouts_and_ABI3_metadata_frame_fixtures_only';normal_receiver_layouts=$values[0];frame_cases=$values[1];suppressed_backtrace_OOM=$values[2];workers=$values[3];parallel_calls=$values[4];kernel_sha256=$kernelHash;
fixture_receivers_and_frames=$true;source_Java_executed=$false;source_native_binding_provided=$false;Java_StackTraceElement_materialization=$false;stack_roots=$false;automatic_gc=$false;game_started=$false;run_directory=$root}
$json=$r|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
