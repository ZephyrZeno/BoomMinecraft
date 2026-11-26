param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
if(-not $installation){throw 'MSVC tools were not found'}
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$root=[IO.Path]::GetFullPath($Output);[IO.Directory]::CreateDirectory($root)|Out-Null
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$(Join-Path $root 'fd-worker.obj')" (Join-Path $projectRoot 'native/probe/fd_worker.asm')
if($LASTEXITCODE -ne 0){throw 'File IO worker assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_entry "/OUT:$(Join-Path $root 'fd-worker.dll')" (Join-Path $root 'fd-worker.obj') (Join-Path $root 'boom-runtime.lib')
if($LASTEXITCODE -ne 0){throw 'File IO worker link failed'}
