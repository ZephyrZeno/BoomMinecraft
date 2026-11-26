param([string]$Output='.boom\class-probe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$destination=[IO.Path]::GetFullPath($Output)
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $destination
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $destination
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um\x64\synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $destination 'class-probe.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" (Join-Path $projectRoot 'native\probe\class_init.asm')
if($LASTEXITCODE -ne 0){throw 'Class probe assembly failed.'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_class_ensure /EXPORT:boom_probe_configure_class /EXPORT:boom_probe_class_initializer /EXPORT:boom_probe_class_failure /EXPORT:boom_probe_class_error /EXPORT:boom_probe_class_floating /EXPORT:boom_probe_ensure_entry "/OUT:$(Join-Path $destination 'class-probe.dll')" $object (Join-Path $destination 'classes.obj') (Join-Path $sdk.FullName 'um\x64\kernel32.lib') (Join-Path $sdk.FullName 'um\x64\synchronization.lib')
if($LASTEXITCODE -ne 0){throw 'Class probe link failed.'}
