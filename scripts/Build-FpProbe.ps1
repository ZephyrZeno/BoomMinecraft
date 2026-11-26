param([string]$Output='.boom\fp-probe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if(-not $installation){throw 'MSVC tools missing.'}
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
$destination=[IO.Path]::GetFullPath($Output)
[IO.Directory]::CreateDirectory($destination)|Out-Null
$object=Join-Path $destination 'fpstate.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" (Join-Path $projectRoot 'native\probe\fpstate.asm')
if($LASTEXITCODE -ne 0){throw 'FP probe assembly failed.'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_probe_numeric /EXPORT:boom_probe_gate /EXPORT:boom_probe_counted "/OUT:$(Join-Path $destination 'fpstate.dll')" $object
if($LASTEXITCODE -ne 0){throw 'FP probe link failed.'}
