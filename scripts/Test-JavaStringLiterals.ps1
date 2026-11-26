param([string]$Runtime='.boom/assembly-runtime-v81',[string]$Output='')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=if($Output){[IO.Path]::GetFullPath($Output)}else{Join-Path $project ('.boom/java-string-literal-tests/'+[guid]::NewGuid().ToString('N'))}
[IO.Directory]::CreateDirectory($root)|Out-Null
$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$assembly=Join-Path $root 'java-string-literals.asm';$object=Join-Path $root 'java-string-literals.obj';$dll=Join-Path $root 'java-string-literals.dll'
$text=[IO.File]::ReadAllText((Join-Path $project 'native/kernels/java_string_literals.inc'))+"`nEND`n"
[IO.File]::WriteAllText($assembly,$text,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" $assembly
if($LASTEXITCODE -ne 0){throw 'Java String literal kernel assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /BREPRO /EXPORT:boom_java_string_literal "/OUT:$dll" $object (Join-Path $runtimePath 'boom-runtime.lib') (Join-Path $sdk.FullName 'um/x64/synchronization.lib')
if($LASTEXITCODE -ne 0){throw 'Java String literal kernel link failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/JavaStringLiteralReference.java')
if($LASTEXITCODE -ne 0){throw 'Java String literal oracle compilation failed'}
Add-Type -Path (Join-Path $project 'tests/host/JavaStringLiteralProbe.cs')
$results=@()
foreach($compact in @($true,$false)) {
    $mode=if($compact){'compact'}else{'utf16'};[string[]]$extra=if($compact){@()}else{@('-XX:-CompactStrings')}
    & "$java/java.exe" -Xmx256m @extra --add-opens java.base/java.lang=ALL-UNNAMED -cp "$root/reference" JavaStringLiteralReference 1> "$root/$mode.tsv" 2> "$root/$mode.err"
    if($LASTEXITCODE -ne 0){throw "Java String literal oracle failed: $mode"}
    foreach($paged in @($false,$true)) {
        $counts=[BoomJavaStringLiteralProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,"$root/$mode.tsv",$compact,$paged)
        $results+=[ordered]@{mode=$mode;paged_entries=$paged;canonical_cases=$counts[0];native_literal_calls=$counts[1];workers=$counts[2]}
    }
}
$result=[ordered]@{passed=$true;scope='assembly_source_layout_String_literal_factory_only';runtime_language='assembly';modes=$results;Latin1_and_UTF16=$true;all_UTF16_units_and_unpaired_surrogates=$true;hot_guest_allocations=0;quiescent_explicit_GC_roots=$true;partial_OOM_and_retry=$true;original_String_Java_bodies_executed=$false;general_String_intern=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $project '.boom/latest-java-string-literal-test.txt'),$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
