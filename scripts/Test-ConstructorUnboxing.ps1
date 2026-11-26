param([Parameter(Mandatory=$true)][string]$Baseline,[Parameter(Mandatory=$true)][string]$WideningRun,
[string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$widening=(Resolve-Path -LiteralPath $WideningRun).Path;$sourceImage=(Resolve-Path -LiteralPath $Baseline).Path
$previous=Get-Content -LiteralPath (Join-Path $widening 'result.json') -Raw|ConvertFrom-Json
$widenKernel=Join-Path $project 'native/providers/constructor_widen.asm.inc'
if(-not $previous.passed -or (Get-FileHash -LiteralPath $widenKernel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $previous.kernel_sha256){throw 'Unboxing requires the verified primitive widening kernel/oracle'}
$kernel=Join-Path $project 'native/providers/constructor_unbox.asm.inc';$kernelHash=(Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant()
$root=Join-Path $project ('.boom/constructor-unboxing-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-constructor-unbox-probe.py') --baseline $sourceImage --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/prepare.err" -Tail 12;throw 'Normal wrapper source metadata failed'}
[IO.File]::WriteAllText("$root/unbox.asm",('option casemap:none'+"`n"+[IO.File]::ReadAllText($kernel)+"`nEND`n"),[Text.UTF8Encoding]::new($false))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$root/unbox.obj" "$root/unbox.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/assembler.log" -Tail 14;throw 'Normal wrapper unboxing assembly failed'}
$wideObject=Join-Path $widening 'widen.obj';$wideHash=(Get-FileHash -LiteralPath $wideObject -Algorithm SHA256).Hash
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /BREPRO "/OUT:$root/unbox.dll" "$root/unbox.obj" $wideObject (Join-Path $runtimePath 'boom-runtime.lib') /EXPORT:boom_constructor_unbox /EXPORT:boom_constructor_widen /EXPORT:boom_widen_probe_get_mxcsr /EXPORT:boom_widen_probe_set_mxcsr > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 14;throw 'Normal wrapper unboxing link failed'}
$check=@'
import importlib.util,sys
from pathlib import Path
p=Path('scripts/verify-batch-assembly.py');spec=importlib.util.spec_from_file_location('actual_unbox_coff',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
d,x=m.coff_symbols(Path(sys.argv[1])/'unbox.obj');assert d=={'boom_constructor_unbox'} and x=={'boom_heap_contains','boom_runtime_row','boom_constructor_widen'}
print('Actual unboxing COFF imports/definitions verified')
'@
$check|& D:/Dev/Python312/python.exe - $root > "$root/coff.log"
if($LASTEXITCODE -ne 0){throw 'Normal wrapper unboxing COFF differs'}
Copy-Item -LiteralPath (Join-Path $widening 'oracle.tsv') -Destination "$root/oracle.tsv"
Add-Type -Path (Join-Path $project 'tests/host/ConstructorUnboxingProbe.cs')
$values=[BoomConstructorUnboxingProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $sourceImage 'diagnostic-image.dll'),"$root/unbox.dll","$root/source.json","$root/oracle.tsv")
if((Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $kernelHash -or (Get-FileHash -LiteralPath $wideObject -Algorithm SHA256).Hash -ne $wideHash){throw 'Unboxing sources/verified widening object changed'}
$result=[ordered]@{passed=$true;scope='normal_source_wrapper_unboxing_and_primitive_widening_only';oracle_cases=$values[0];
MXCSR_variants=5;conversion_checks=$values[1];error_checks=$values[2];workers=$values[3];parallel_calls=$values[4];
kernel_sha256=$kernelHash;normal_heap_unboxing_verified=$true;fixture_wrapper_objects=$true;Java_wrapper_constructors_executed=$false;
source_native_binding_provided=$false;target_constructor_invoked_by_ASM=$false;game_started=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
