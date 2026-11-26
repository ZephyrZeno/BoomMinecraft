param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v81/boom-runtime.dll',[string]$ExistingRun='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=if($ExistingRun){[IO.Path]::GetFullPath($ExistingRun)}else{Join-Path (Get-Location) ('.boom/shutdown-tests/'+[guid]::NewGuid().ToString('N'))};[IO.Directory]::CreateDirectory($root)|Out-Null
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$modules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json
if(-not $ExistingRun){
 & $Boom compile-locked-program --lock .boom/locks/server.json --jdk-base $base --jdk-modules $modules --entry-class java/lang/Shutdown --method halt --descriptor '(I)V' --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
 if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 8;throw 'Shutdown AOT compilation failed'}
}
& D:/Dev/Python312/python.exe scripts/verify-shutdown.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Shutdown source contract failed'}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d "$root/classes" java/reference/ShutdownHaltReference.java
if($LASTEXITCODE -ne 0){throw 'Shutdown oracle javac failed'}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
Add-Type -Path tests/host/ShutdownProbe.cs
[BoomShutdownProbe]::EventChecks($p.compilation.dll,[IO.Path]::GetFullPath($Runtime))
function Run-OwnedChild([string]$exe,[string[]]$arguments,[string]$label){
 $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$exe;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
 foreach($arg in $arguments){$info.ArgumentList.Add($arg)}
 foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
 $child=[Diagnostics.Process]::new();$child.StartInfo=$info
 try{if(-not $child.Start()){throw "$label did not start"};$stdout=$child.StandardOutput.ReadToEndAsync();$stderr=$child.StandardError.ReadToEndAsync();if(-not $child.WaitForExit(15000)){$child.Kill($true);$child.WaitForExit();throw "$label timeout"};$err=$stderr.GetAwaiter().GetResult();$out=$stdout.GetAwaiter().GetResult();[IO.File]::WriteAllText("$root/$label.out",$out);[IO.File]::WriteAllText("$root/$label.err",$err);if($err){throw "$label wrote stderr: $err"};return $child.ExitCode}finally{$child.Dispose()}
}
$childScript=[IO.Path]::GetFullPath('tests/host/RunShutdownChild.ps1');$shell=(Get-Process -Id $PID).Path;$statuses=@(0,1,23,255,-1,[int]::MinValue,[int]::MaxValue)
$results=@(foreach($status in $statuses){
 $expected=Run-OwnedChild 'D:/Dev/Java/jdk-21/bin/java.exe' @('-Xmx128m',"-XX:ErrorFile=$root/hs_err_pid%p.log",'--add-opens=java.base/java.lang=ALL-UNNAMED','-cp',"$root/classes",'ShutdownHaltReference',"$status") "jvm-$status"
 $actual=Run-OwnedChild $shell @('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$childScript,'-Image',$p.compilation.dll,'-Runtime',[IO.Path]::GetFullPath($Runtime),'-Code',"$status") "native-$status"
 if($actual -ne $expected -or $actual -ne $status){throw "Shutdown exit status differs: requested=$status JVM=$expected native=$actual"};[ordered]@{requested=$status;JVM=$expected;native=$actual}
})
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Shutdown compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_exit_cases=7;owned_native_child_processes=7;original_Shutdown_initializer_Lock_constructor_and_halt_monitor_executed=$true;original_Java_beforeHalt_caller_executed=$false;original_runHooks_executed=$false;native_beforeHalt_event_workers=8;native_beforeHalt_events=8192;event_guest_allocations=0;pending_bad_metadata_and_missing_status_rejected=$true;JFR_supported=$false;exit_results=$results;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-shutdown-test.txt',$root);Write-Output $json
exit 0
