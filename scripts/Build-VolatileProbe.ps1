param([string]$Output='.boom\volatile-probe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
if(-not $installation){throw 'MSVC tools missing'}
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um\x64\kernel32.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$destination=[IO.Path]::GetFullPath($Output);[IO.Directory]::CreateDirectory($destination)|Out-Null
$object=Join-Path $destination 'volatile-probe.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" (Join-Path $projectRoot 'native\probe\volatile.asm')
if($LASTEXITCODE -ne 0){throw 'Volatile harness assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_volatile_stress "/OUT:$(Join-Path $destination 'volatile-probe.dll')" $object (Join-Path $sdk.FullName 'um\x64\kernel32.lib')
if($LASTEXITCODE -ne 0){throw 'Volatile harness link failed'}
