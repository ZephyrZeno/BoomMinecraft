param([Parameter(Mandatory=$true)][string]$PreparedSource,[Parameter(Mandatory=$true)][string]$WideningRun,
[Parameter(Mandatory=$true)][string]$UnboxingSource,[string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$prepared=(Resolve-Path -LiteralPath $PreparedSource).Path;$wide=(Resolve-Path -LiteralPath $WideningRun).Path
$root=Join-Path $project ('.boom/constructor-callsite-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$m=Get-Content -LiteralPath (Join-Path $prepared 'link-source.json') -Raw|ConvertFrom-Json
$source=Get-Content -LiteralPath (Join-Path $prepared 'source.json') -Raw|ConvertFrom-Json
$acceptedPath=$m.accepted_framed_manifest.path
if((Get-FileHash -LiteralPath $acceptedPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $m.accepted_framed_manifest.digest.sha256){throw 'Accepted constructor source image changed'}
$wideResult=Get-Content -LiteralPath (Join-Path $wide 'result.json') -Raw|ConvertFrom-Json
if(-not $wideResult.passed -or (Get-FileHash -LiteralPath (Join-Path $project 'native/providers/constructor_widen.asm.inc') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $wideResult.kernel_sha256){throw 'Constructor call-site widening kernel changed'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10;$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$kernelFiles=@('constructor_unbox','constructor_callsite');$objects=@();$hashes=[ordered]@{}
foreach($name in $kernelFiles){$kernel=Join-Path $project ('native/providers/'+$name+'.asm.inc');$hashes[$name]=(Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant();[IO.File]::WriteAllText("$root/$name.asm",('option casemap:none'+"`n"+[IO.File]::ReadAllText($kernel)+"`nEND`n"),[Text.UTF8Encoding]::new($false));$objects+="$root/$name.obj"}
Copy-Item -LiteralPath (Join-Path $prepared 'sites.asm') -Destination "$root/sites.asm";$objects+="$root/sites.obj"
foreach($name in @('constructor_unbox','constructor_callsite','sites')){& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$root/$name.obj" "$root/$name.asm" > "$root/$name-assembler.log" 2>&1;if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/$name-assembler.log" -Tail 14;throw 'Source constructor probe assembly failed'}}
$objects+=(Join-Path $wide 'widen.obj');$objects+=@($m.objects)
$exports=@($m.exports)+@('boom_constructor_callsite','boom_constructor_probe_call','boom_constructor_probe_sites','boom_constructor_widen','boom_constructor_unbox','boom_widen_probe_get_mxcsr','boom_widen_probe_set_mxcsr')
$dll=Join-Path $root 'constructors.dll';$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'))
$lines+=@($objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"');$lines+=@($exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_})
[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 18;throw 'Source constructor probe link failed'}
Copy-Item -LiteralPath (Join-Path $prepared 'source.json') -Destination "$root/source.json"
Add-Type -Path (Join-Path $project 'tests/host/ConstructorCallsiteProbe.cs')
$values=[BoomConstructorCallsiteProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,"$root/source.json",$UnboxingSource,(Join-Path $wide 'oracle.tsv'))
foreach($name in $kernelFiles){if((Get-FileHash -LiteralPath (Join-Path $project ('native/providers/'+$name+'.asm.inc')) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hashes[$name]){throw 'Constructor kernel changed during execution'}}
$result=[ordered]@{passed=$true;scope='source_JDK_constructor_callsite_kernel_with_original_Java_bodies';source_sites=$values[0];accepted_primitive_constructors=$values[1];rejected_primitive_arguments=$values[2];
cold_original_class_initializations=$values[3];original_constructor_body_errors=$values[4];pre_call_errors=$values[5];workers=$values[6];parallel_calls=$values[7];
kernel_sha256=$hashes;target_constructor_invoked_by_ASM=$true;reference_arguments_verified=$true;source_native_binding_provided=$false;exception_wrapping_complete=$false;full_module_bootstrap=$false;
Java_ASM_or_COFF_modified=$false;Java_reassembled_in_this_probe=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
