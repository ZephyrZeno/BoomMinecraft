param([string]$Output='')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=if($Output){[IO.Path]::GetFullPath($Output)}else{Join-Path $project ('.boom/floating-remainder-tests/'+[guid]::NewGuid().ToString('N'))}
[IO.Directory]::CreateDirectory($root)|Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
if(-not $installation){throw 'MSVC tools missing'}
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$assembly=Join-Path $root 'floating-remainder.asm'
$object=Join-Path $root 'floating-remainder.obj'
$dll=Join-Path $root 'floating-remainder.dll'
$text=[IO.File]::ReadAllText((Join-Path $project 'native/kernels/floating_remainder.inc'))+"`nPUBLIC boom_frem32`nPUBLIC boom_frem64`nEND`n"
[IO.File]::WriteAllText($assembly,$text,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" $assembly
if($LASTEXITCODE -ne 0){throw 'Remainder kernel assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /BREPRO /EXPORT:boom_frem32 /EXPORT:boom_frem64 "/OUT:$dll" $object
if($LASTEXITCODE -ne 0){throw 'Remainder kernel link failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -d "$root/classes" java/reference/FloatingRemainderReference.java
if($LASTEXITCODE -ne 0){throw 'Remainder oracle compilation failed'}
& "$java/java.exe" -Xmx128m -cp "$root/classes" FloatingRemainderReference 1> "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Remainder oracle execution failed'}
Add-Type -Path tests/host/FloatingRemainderProbe.cs
$counts=[BoomFloatingRemainderProbe]::Run($dll,"$root/oracle.tsv")
$result=[ordered]@{passed=$true;scope='assembly_frem_drem_kernel_only';single_cases=$counts[0];double_cases=$counts[1];JVM_cases=$counts[2];native_executions=$counts[3];workers=8;NaN_payload_policy='canonical_quiet_NaN';runtime_language='assembly';game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json
[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-floating-remainder-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
