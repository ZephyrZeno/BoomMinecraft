param([Parameter(Mandatory=$true)][string]$Baseline,[Parameter(Mandatory=$true)][string]$Adapters,
[string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/framed-provider-tests/'+[guid]::NewGuid().ToString('N'));$image=Join-Path $root 'image'
[IO.Directory]::CreateDirectory($root)|Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$linker=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64/link.exe"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$synchronization=Join-Path $sdk.FullName 'um/x64/synchronization.lib'
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'relink-framed-diagnostic.py') --baseline $Baseline --adapters $Adapters --runtime $runtimePath --output $image --linker $linker --synchronization $synchronization > "$root/relink.log" 2> "$root/relink.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/relink.err" -Tail 16;Get-Content -LiteralPath "$image/link.log" -Tail 12 -ErrorAction SilentlyContinue;throw 'Framed native diagnostic relink failed'}
$hostSource=Join-Path $project 'tests/host/FramedNativeProviderProbe.cs'
$hostHash=(Get-FileHash -LiteralPath $hostSource -Algorithm SHA256).Hash.ToLowerInvariant()
Add-Type -Path $hostSource
$values=[BoomFramedNativeProviderProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'framed-image.dll'),(Join-Path $image 'source.json'))
if((Get-FileHash -LiteralPath $hostSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hostHash){throw 'Framed native FFI host changed during execution'}
$result=[ordered]@{passed=$true;scope='framed_source_native_entries_and_original_cold_reflection_initializer_upcalls';
cases=$values[0];distinct_raw_and_modifier_cases=$values[1];array_cases=$values[2];error_checks=$values[3];workers=$values[4];parallel_calls=$values[5];
original_Object_constructor_enumerations=$values[6];cold_original_reflection_initializations=$values[7];
direct_framed_native_entries_exercised=3;fixture_loaders=2;fixture_modules=63;full_module_bootstrap=$false;
FFI_host_sha256=$hostHash;Java_codegen_rerun=$false;Java_ASM_or_COFF_modified=$false;Java_reassembled_in_this_relink=$false;
diagnostic_only=$true;all_native_frames=$false;automatic_gc=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
