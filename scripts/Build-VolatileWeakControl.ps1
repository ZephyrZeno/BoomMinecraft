param([Parameter(Mandatory=$true)][string]$Program,[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$programPath=(Resolve-Path -LiteralPath $Program).Path
$destination=[IO.Path]::GetFullPath($Output);[IO.Directory]::CreateDirectory($destination)|Out-Null
$source=Get-Content -LiteralPath (Join-Path $programPath 'method.asm') -Raw
$pattern='(?m)^([ \t]*)xchg ([^\r\n]+?) ; volatile SC store\r?$'
$count=[regex]::Matches($source,$pattern).Count
if($count -eq 0){throw 'No generated volatile stores were found for the negative control'}
$weak=[regex]::Replace($source,$pattern,'$1mov $2 ; TEST ONLY: removed volatile ordering')
$assembly=Join-Path $destination 'weak.asm';[IO.File]::WriteAllText($assembly,$weak,[Text.UTF8Encoding]::new($false))
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um\x64\kernel32.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $destination 'weak.obj'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" $assembly
if($LASTEXITCODE -ne 0){throw 'Negative-control assembly failed'}
$objects=@($object,(Join-Path $programPath 'classes-runtime.obj'))+@(Get-ChildItem -LiteralPath (Join-Path $programPath 'runtime') -Filter '*.obj' -File|ForEach-Object FullName)
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_entry /EXPORT:boom_bind_heap /EXPORT:boom_heap_create /EXPORT:boom_heap_collect /EXPORT:boom_heap_destroy /EXPORT:boom_get_static_roots "/OUT:$(Join-Path $destination 'weak.dll')" @objects (Join-Path $sdk.FullName 'um\x64\kernel32.lib') (Join-Path $sdk.FullName 'um\x64\synchronization.lib')
if($LASTEXITCODE -ne 0){throw 'Negative-control link failed'}
$receipt=[ordered]@{test_only=$true;deliberately_incorrect_volatile_ordering=$true;removed_ordered_stores=$count;positive_assembly_sha256=(Get-FileHash -LiteralPath (Join-Path $programPath 'method.asm') -Algorithm SHA256).Hash.ToLowerInvariant();negative_assembly_sha256=(Get-FileHash -LiteralPath $assembly -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $destination 'control.json'),($receipt|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
