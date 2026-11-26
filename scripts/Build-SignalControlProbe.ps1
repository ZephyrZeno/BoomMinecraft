param([string]$Output='.boom/signal-control-probe')
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
$object=Join-Path $destination signal-control-probe.obj
& (Join-Path $bin ml64.exe) /nologo /c "/Fo$object" (Join-Path $projectRoot native/probe/signal_control_probe.asm)
if($LASTEXITCODE -ne 0){throw 'Signal control test callback assembly failed'}
$exports=@('dispatch','break','native','bind','register_job','raise_job','enter','exit','lifecycle_dispatch')|ForEach-Object {"/EXPORT:boom_signal_test_$_"}
& (Join-Path $bin link.exe) /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT @exports "/OUT:$(Join-Path $destination signal-control-probe.dll)" $object (Join-Path $destination boom-runtime.lib) (Join-Path $sdk.FullName um/x64/kernel32.lib)
if($LASTEXITCODE -ne 0){throw 'Signal control callback link failed'}
$console=Join-Path $destination signal-console.obj
& (Join-Path $bin ml64.exe) /nologo /c "/Fo$console" (Join-Path $projectRoot native/probe/signal_console.asm)
if($LASTEXITCODE -ne 0){throw 'Signal console test assembly failed'}
& (Join-Path $bin link.exe) /NOLOGO /MACHINE:X64 /SUBSYSTEM:CONSOLE /ENTRY:signal_console_main /DYNAMICBASE /NXCOMPAT "/OUT:$(Join-Path $destination signal-console.exe)" $console (Join-Path $destination boom-runtime.lib) (Join-Path $sdk.FullName um/x64/kernel32.lib)
if($LASTEXITCODE -ne 0){throw 'Signal console test link failed'}
foreach($number in @(2,4,6,8,11,15,22)){
    & (Join-Path $bin link.exe) /NOLOGO /MACHINE:X64 /SUBSYSTEM:CONSOLE "/ENTRY:signal_default_$number" /DYNAMICBASE /NXCOMPAT "/OUT:$(Join-Path $destination ('signal-default-'+$number+'.exe'))" $console (Join-Path $destination boom-runtime.lib) (Join-Path $sdk.FullName um/x64/kernel32.lib)
    if($LASTEXITCODE -ne 0){throw 'Default signal test link failed'}
}
