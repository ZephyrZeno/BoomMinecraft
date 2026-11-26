param([string]$Output='dist\native',[string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$outputPath=[IO.Path]::GetFullPath($Output)
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $outputPath
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw | ConvertFrom-Json
$javac=Join-Path (Split-Path -Parent $tools.java) 'javac.exe'
$classes=Join-Path $outputPath 'fixture-classes'
[IO.Directory]::CreateDirectory($classes) | Out-Null
& $javac --release 21 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\IntKernels.java')
if($LASTEXITCODE -ne 0) { throw 'Cannot compile Java input fixture.' }
$kernel=Join-Path $outputPath 'kernel'
& $Boom compile-asm --class-file (Join-Path $classes 'dev\boom\subset\IntKernels.class') --method parallelWork --output $kernel --assemble | Out-Null
if($LASTEXITCODE -ne 0) { throw 'Cannot generate the fixture assembly.' }
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'um\x64\kernel32.lib') } | Sort-Object Name -Descending | Select-Object -First 1
$object=Join-Path $outputPath 'probe.obj'
$executable=Join-Path $outputPath 'boom-native-probe.exe'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" (Join-Path $projectRoot 'native\probe\main.asm')
if($LASTEXITCODE -ne 0) { throw 'Probe assembly failed.' }
& (Join-Path $bin 'link.exe') /NOLOGO /SUBSYSTEM:CONSOLE /ENTRY:boom_probe_main /MACHINE:X64 /DYNAMICBASE /NXCOMPAT "/OUT:$executable" $object (Join-Path $outputPath 'parallel.obj') (Join-Path $kernel 'method.obj') (Join-Path $sdk.FullName 'um\x64\kernel32.lib')
if($LASTEXITCODE -ne 0) { throw 'Probe link failed.' }
& $executable
if($LASTEXITCODE -ne 0) { throw 'Standalone assembly probe failed.' }
& (Join-Path $bin 'dumpbin.exe') /DEPENDENTS $executable | Set-Content -LiteralPath (Join-Path $outputPath 'probe-dependencies.txt')
Write-Output "Standalone assembly executable: $executable"
