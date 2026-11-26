param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$Runtime='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/notification-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-notification-test.txt',$root)
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/notifications/NotifyProgram.java java/reference/NotifyReference.java
if($LASTEXITCODE -ne 0){throw 'Notification fixture/reference javac failed'}
$programs=@{}
foreach($method in @('run','fail')){
 $descriptor=if($method -eq 'run'){'(I)I'}else{'(Ljava/lang/Object;)V'}
 $arguments=@('compile-program','--entry-class','dev/boom/notifications/NotifyProgram','--method',$method,'--descriptor',$descriptor,'--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',(Join-Path $root $method),'--assemble')
 foreach($file in Get-ChildItem (Join-Path $classes dev/boom/notifications) -Filter '*.class'){$arguments+=@('--class-file',$file.FullName)}
 & $Boom @arguments > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
 if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 8;throw 'Notification compilation failed'}
 & D:/Dev/Python312/python.exe scripts/verify-notifications.py (Join-Path $root "$method/program.json") $JdkBase > (Join-Path $root ($method+'-source-contract.json'))
 if($LASTEXITCODE -ne 0){throw 'Notification independent source proof failed'}
 $programs[$method]=Get-Content (Join-Path $root "$method/program.json") -Raw|ConvertFrom-Json
}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'NotifyReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Notification JVM oracle failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Notification JVM timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
Add-Type -Path tests/host/NotifyProbe.cs
$actual=[BoomNotifyProbe]::Run($programs.run.compilation.dll)
if(($actual -join '|') -cne ($expected -join '|')){throw "Notification/JVM differs: $($actual -join ',') vs $($expected -join ',')"}
if($Runtime){$packaged=[BoomNotifyProbe]::Run($programs.run.compilation.dll,(Resolve-Path $Runtime).Path);if(($actual -join '|') -cne ($packaged -join '|')){throw 'Notification full DLL differs'}}
$p=$programs.fail;$illegal=@($p.exception_runtime.factories|Where-Object kind -eq 17)[0].class_id;$npeClass=@($p.exception_runtime.factories|Where-Object kind -eq 4)[0].class_id
[BoomNotifyProbe]::Failure($p.compilation.dll,[uint32]$illegal,[uint32]$npeClass,[uint32]$p.entry_id)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Notification compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=2;JVM_cases=$expected.Count;full_runtime_tested=[bool]$Runtime;full_runtime_sha256=$(if($Runtime){(Get-FileHash $Runtime).Hash.ToLowerInvariant()}else{''});empty_wait_sets_tested=$true;shared_wait_set_runtime_verified=$true;source_native_declarations_verified=$true;source_wait0_executed=$false;Java_interruption_implemented=$false;unsupported_nonempty_wait_metadata_fails_explicitly=$true;parallel_workers=8;parallel_generated_calls=1024;recursive_ownership_preserved=$true;entry_contender_not_released_by_notification=$true;owner_thread_required=$true;null_unowned_foreign_objects_checked=$true;pending_context_preserved=$true;actual_Throwable_and_source_PC_checked=$true;full_heap_notifications_zero_allocation=$true;explicit_reclamation_checked=$true;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-notification-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
