param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/platform-startup-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-platform-startup-test.txt',$root)
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$classes=Join-Path $root classes
foreach($file in $inputs.java.runtime_files){if((Get-FileHash $file.path).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Platform oracle JDK differs from lock'}}
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -proc:none -d $classes java/reference/SignalControlReference.java java/reference/WindowsStartupReference.java
if($LASTEXITCODE -ne 0){throw 'Platform startup oracle javac failed'}
function Java([string]$entry,[string[]]$values){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('--add-opens','java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens','java.base/sun.io=ALL-UNNAMED','-Xmx128m','-cp',$classes,$entry)+$values){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Platform JVM oracle failed'};$out=$java.StandardOutput.ReadToEndAsync();$err=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Platform JVM oracle timeout'};if($java.ExitCode -ne 0){throw $err.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
Java SignalControlReference @((Join-Path $root registration.bin),(Join-Path $root thread-local.bin))
Java WindowsStartupReference @((Join-Path $root windows.bin))
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-SignalControlProbe.ps1 -Output $root *> (Join-Path $root adapter-build.log)
& $Boom inspect-signal-runtime --lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root signal-contract) > (Join-Path $root signal-contract.json) 2> (Join-Path $root signal-contract.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root signal-contract.err) -Tail 8;throw 'Signal control source inspection failed'}
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class sun/io/Win32ErrorMode --method setErrorMode --descriptor '(J)J' --output (Join-Path $root error-mode) --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 10;throw 'Native Windows error-mode entry compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-platform-startup.py (Join-Path $root signal-contract/inspection.json) (Join-Path $root error-mode/program.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent platform source verification failed'}
Add-Type -Path tests/host/PlatformStartupProbe.cs
[BoomPlatformStartupProbe]::Signals((Join-Path $root boom-runtime.dll),(Join-Path $root signal-control-probe.dll),(Join-Path $root registration.bin))
$p=Get-Content (Join-Path $root error-mode/program.json) -Raw|ConvertFrom-Json
[BoomPlatformStartupProbe]::ErrorMode($p.compilation.dll,(Join-Path $root boom-runtime.dll),(Join-Path $root windows.bin))
& D:/Dev/Python312/python.exe scripts/make-platform-private-fixtures.py (Join-Path $root private)
if($LASTEXITCODE -ne 0){throw 'Private platform fixture generation failed'}
foreach($name in @('PrivateHandle','PrivateRaise','PrivateMode')){
    $reason=(& $Boom compile-program --class-file (Join-Path $root "private/$name.class") --entry-class "dev/boom/platform/$name" --method run --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root "rejected-$name") --assemble 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or $reason -notmatch 'native is private to its original'){throw "Private platform access was not rejected: $reason"}
    [IO.File]::WriteAllText((Join-Path $root "private-$name.txt"),$reason,[Text.UTF8Encoding]::new($false))
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Platform compiler changed during tests'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';signal_native_bridge_JVM_registration_cases=4096;signal_bridge_parallel_workers=8;signal_bridge_async_callbacks=2057;signal_bridge_native_callback_leases_checked=$true;live_transport_required_and_close_before_unbind_checked=$true;pending_context_and_private_source_contracts_checked=$true;application_private_native_calls_rejected=3;Win32ErrorMode_native_AOT_entries=1;Win32ErrorMode_JVM_cases=256;Windows_UINT_truncation_and_previous_mode_checked=$true;test_process_error_mode_restored=$true;Signal_VM_callbacks_are_assembly_fixtures=$true;original_Signal_dispatch_executed=$false;original_Signal_Java_initializer_executed=$false;original_Win32ErrorMode_initialize_executed=$false;System_boot_phases_completed=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-platform-startup-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
