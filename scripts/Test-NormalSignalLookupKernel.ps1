param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/normal-signal-kernel-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-normal-signal-lookup-test.py') --directory $Directory --accepted-verification-sha256 $AcceptedVerificationSha256 --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 14;throw 'Normal signal kernel source preparation failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
function Assert-Inputs {foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('Normal signal kernel input changed: '+$r.path)}}}
Assert-Inputs
$java='D:/Dev/Java/jdk-21/bin/java.exe';$javac='D:/Dev/Java/jdk-21/bin/javac.exe';$classes=Join-Path $root classes
& $javac --release 21 -g -proc:none -encoding UTF-8 -d $classes (Join-Path $project 'java/subset/dev/boom/signals/SignalNames.java') (Join-Path $project 'java/reference/SignalNamesReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/javac.log" -Tail 10;throw 'Signal reference compilation failed'}
$start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$java;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
foreach($a in @('--add-opens','java.base/jdk.internal.misc=ALL-UNNAMED','-Xmx128m','-cp',$classes,'SignalNamesReference',"$root/raw.bin","$root/literals.bin")){$start.ArgumentList.Add($a)}
foreach($name in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$start.Environment.Remove($name)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$start
try{if(-not $oracle.Start()){throw 'Cannot start signal JVM reference'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync();if(-not $oracle.WaitForExit(45000)){$oracle.Kill($true);throw 'Signal JVM reference exceeded 45 seconds'};[IO.File]::WriteAllText("$root/oracle.log",$stdout.GetAwaiter().GetResult()+$stderr.GetAwaiter().GetResult());if($oracle.ExitCode -ne 0){Get-Content "$root/oracle.log" -Tail 12;throw 'Signal JVM reference failed'}}finally{$oracle.Dispose()}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$root/signal.obj" "$root/signal.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 14;throw 'Normal signal kernel assembly failed'}
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /BREPRO "/OUT:$root/signal.dll" "$root/signal.obj" (Join-Path (Split-Path $m.runtime -Parent) 'boom-runtime.lib') /EXPORT:boom_provider_signal_lookup_service /EXPORT:boom_provider_signal_lookup_pool /EXPORT:boom_heap_ptr /EXPORT:boom_java_string_literal_pool > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 12;throw 'Normal signal kernel link failed'}
Add-Type -Path (Join-Path $project 'tests/host/NormalSignalLookupKernelProbe.cs')
$v=[BoomNormalSignalLookupKernelProbe]::Run("$root/source.json","$root/signal.dll","$root/raw.bin","$root/literals.bin")
Assert-Inputs
$result=[ordered]@{passed=$true;scope='staged_Windows_signal_name_lookup_over_normal_source_layout_String_fixtures_only';JVM_oracle_used_only_for_reference=$true;literal_cases=$v[0];raw_UTF16_cases=$v[1];error_checks=$v[2];workers=$v[3];parallel_calls=$v[4];lookup_guest_allocations=0;fixture_objects_and_String_pool_copy=$true;source_native_entries_executed=$false;Java_initializers_executed=$false;handler_installation=$false;signal_raise=$false;Java_signal_dispatch=$false;game_started=$false;world_created=$false;source_configuration="$root/source.json";artifacts=@('signal.asm','signal.obj','signal.dll','raw.bin','literals.bin'|ForEach-Object{[ordered]@{path=(Join-Path $root $_);sha256=(Get-FileHash -LiteralPath (Join-Path $root $_) -Algorithm SHA256).Hash.ToLowerInvariant()}});run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
