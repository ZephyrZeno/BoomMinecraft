param([string]$Output='.boom/thread-registry-probe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
if(-not $installation){throw 'MSVC tools missing'}
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:/SOFTWARE/Microsoft/Windows Kits/Installed Roots').KitsRoot10
$sdk=Get-ChildItem (Join-Path $sdkRoot Lib) -Directory|Where-Object {Test-Path (Join-Path $_.FullName um/x64/kernel32.lib)}|Sort-Object Name -Descending|Select-Object -First 1
$destination=[IO.Path]::GetFullPath($Output);[IO.Directory]::CreateDirectory($destination)|Out-Null
$object=Join-Path $destination thread-registry-probe.obj
& (Join-Path $bin ml64.exe) /nologo /c "/Fo$object" (Join-Path $projectRoot native/probe/thread_registry_probe.asm)
if($LASTEXITCODE -ne 0){throw 'Thread registry adapter assembly failed'}
$exports=@('main','failure','exit','id_job','publish','rollback','publication_main','publication_exit','publication_failure')|ForEach-Object {"/EXPORT:boom_thread_test_$_"}
& (Join-Path $bin link.exe) /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT @exports "/OUT:$(Join-Path $destination thread-registry-probe.dll)" $object (Join-Path $destination boom-runtime.lib) (Join-Path $sdk.FullName um/x64/kernel32.lib)
if($LASTEXITCODE -ne 0){throw 'Thread registry adapter link failed'}
