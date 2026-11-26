param()
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/constructor-widening-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$kernel=Join-Path $project 'native/providers/constructor_widen.asm.inc';$kernelHash=(Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant()
$probe=@'
.code
PUBLIC boom_widen_probe_get_mxcsr
boom_widen_probe_get_mxcsr PROC FRAME
 sub rsp,8
 .allocstack 8
 .endprolog
 stmxcsr DWORD PTR [rsp]
 mov eax,DWORD PTR [rsp]
 add rsp,8
 ret
boom_widen_probe_get_mxcsr ENDP
PUBLIC boom_widen_probe_set_mxcsr
boom_widen_probe_set_mxcsr PROC FRAME
 sub rsp,8
 .allocstack 8
 .endprolog
 mov DWORD PTR [rsp],ecx
 ldmxcsr DWORD PTR [rsp]
 add rsp,8
 ret
boom_widen_probe_set_mxcsr ENDP
END
'@
$asm='option casemap:none'+"`n"+[IO.File]::ReadAllText($kernel)+"`n"+$probe+"`n"
[IO.File]::WriteAllText("$root/widen.asm",$asm,[Text.UTF8Encoding]::new($false))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$assembler=Join-Path $bin 'ml64.exe';$linker=Join-Path $bin 'link.exe'
$assemblerHash=(Get-FileHash -LiteralPath $assembler -Algorithm SHA256).Hash;$linkerHash=(Get-FileHash -LiteralPath $linker -Algorithm SHA256).Hash
& $assembler /nologo /c "/Fo$root/widen.obj" "$root/widen.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/assembler.log" -Tail 12;throw 'Constructor widening assembly failed'}
& $linker /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /BREPRO "/OUT:$root/widen.dll" "$root/widen.obj" /EXPORT:boom_constructor_widen /EXPORT:boom_widen_probe_get_mxcsr /EXPORT:boom_widen_probe_set_mxcsr > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 12;throw 'Constructor widening link failed'}
$check=@'
import importlib.util,sys
from pathlib import Path
p=Path('scripts/verify-batch-assembly.py');spec=importlib.util.spec_from_file_location('actual_widen_coff',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
defined,undefined=m.coff_symbols(Path(sys.argv[1])/'widen.obj')
assert defined=={'boom_constructor_widen','boom_widen_probe_get_mxcsr','boom_widen_probe_set_mxcsr'} and not undefined
print('Actual AMD64 COFF exports/imports verified')
'@
$check|& D:/Dev/Python312/python.exe - $root > "$root/coff.log"
if($LASTEXITCODE -ne 0){throw 'Constructor widening actual COFF differs'}
[IO.Directory]::CreateDirectory("$root/reference")|Out-Null
& D:/Dev/Java/jdk-21/bin/javac.exe -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/ConstructorWideningReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/javac.log" -Tail 12;throw 'Constructor widening oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe -cp "$root/reference" ConstructorWideningReference > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/oracle.err" -Tail 12;throw 'Constructor widening oracle failed'}
Add-Type -Path (Join-Path $project 'tests/host/ConstructorWideningProbe.cs')
$values=[BoomConstructorWideningProbe]::Run("$root/widen.dll","$root/oracle.tsv")
if((Get-FileHash -LiteralPath $kernel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $kernelHash -or (Get-FileHash -LiteralPath $assembler -Algorithm SHA256).Hash -ne $assemblerHash -or (Get-FileHash -LiteralPath $linker -Algorithm SHA256).Hash -ne $linkerHash){throw 'Constructor widening sources/tools changed during test'}
$result=[ordered]@{passed=$true;scope='primitive_reflection_argument_widening_ASM_helper_only';oracle_cases=$values[0];accepted_cases=$values[1];rejected_cases=$values[2];
MXCSR_variants=5;conversion_checks=$values[3];error_checks=$values[4];workers=$values[5];parallel_calls=$values[6];
kernel_sha256=$kernelHash;source_native_binding_provided=$false;normal_heap_unboxing_verified=$false;target_constructor_invoked_by_ASM=$false;game_started=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
