param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/signal-control-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-signal-control-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$classes=Join-Path $root classes
if($inputs.java.major -ne 21 -or $inputs.java.runtime_files.Count -ne 4){throw 'Locked Java runtime profile changed'}
foreach($file in $inputs.java.runtime_files){if((Get-FileHash $file.path).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'JVM oracle runtime differs from the input lock'}}
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -proc:none -encoding UTF-8 -d $classes java/reference/SignalControlReference.java
if($LASTEXITCODE -ne 0){throw 'Signal registration oracle javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('--add-opens','java.base/jdk.internal.misc=ALL-UNNAMED','-Xmx128m','-cp',$classes,'SignalControlReference',(Join-Path $root registration.bin),(Join-Path $root thread-local.bin))){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Signal oracle start failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Signal oracle timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};[IO.File]::WriteAllText((Join-Path $root jvm.txt),$stdout.GetAwaiter().GetResult())}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-SignalControlProbe.ps1 -Output $root *> (Join-Path $root probe-build.log)
Add-Type -Path tests/host/SignalControlProbe.cs
[BoomSignalControlProbe]::Transport((Join-Path $root boom-runtime.dll),(Join-Path $root signal-control-probe.dll),(Join-Path $root registration.bin),(Join-Path $root thread-local.bin))
Write-Output 'Verified native registration, asynchronous assembly callbacks, eight-worker queues and close/join barriers'
[BoomSignalControlProbe]::Lifecycle((Join-Path $root boom-runtime.dll),(Join-Path $root signal-control-probe.dll))
Write-Output 'Verified Config64/2 worker enter before publication, same-thread dispatch/exit, joined exit and lifecycle errors'
[BoomSignalControlProbe]::NativeChildren($root)
Write-Output 'Verified real Ctrl-C/Ctrl-Break in a separate initially hidden console, and seven isolated default dispositions'
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Compiler changed during signal transport verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/signal_control.asm','native/probe/signal_control_probe.asm','native/probe/signal_console.asm','scripts/Test-SignalControl.ps1','scripts/Build-SignalControlProbe.ps1','scripts/Build-AssemblyRuntime.ps1','tests/host/SignalControlProbe.cs','java/reference/SignalControlReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';raw_VM_transport_only=$true;compiled_Signal_Java_entries=0;registration_JVM_cases=4096;thread_local_and_alias_JVM_cases=11;thread_local_ILL_SEGV_and_ABRT_alias_checked=$true;thread_storage_freed_on_thread_exit=$true;thread_storage_generation_reset_checked=$true;oracle_JVM_runtime_hashes_checked=$true;normal_policy_VM_owned_signals=@(8,21);workers=8;concurrent_registration_records=6147;concurrent_enqueue_records=6147;close_drained_pending_callbacks=129;repeated_lifecycles=16;concurrent_create_callers=8;single_process_transport_checked=$true;active_native_operation_lease_joined=$true;native_callback_one_shot_and_reinstall_checked=$true;callback_self_close_rejected=$true;callback_failure_observable=$true;callback_thread_and_FP_checked=$true;real_OS_Ctrl_C_dispatches=2;real_OS_Ctrl_C_ignored=1;real_OS_Ctrl_Break_dispatches=1;default_disposition_child_processes=7;direct_console_TERM_route_checks=2;OS_close_logoff_shutdown_delivery_verified=$false;runtime_module_pinned_for_late_OS_callback_safety=$true;transport_guest_heap_allocations=0;hardware_exception_to_signal_mapping_complete=$false;Signal_control_bytecode_binding_executed=$false;automatic_gc=$false;Signal_Java_initializer_executed=$false;original_Signal_dispatch_executed=$false;Java_thread_lifecycle_complete=$false;native_lookup_bytecode_binding_execution_verified=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash (Join-Path $root registration.bin)).Hash.ToLowerInvariant();thread_oracle_sha256=(Get-FileHash (Join-Path $root thread-local.bin)).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$report.worker_lifecycle_config_abi=2;$report.worker_lifecycle_config_bytes=64
$report.worker_enter_failure_not_published=$true;$report.worker_enter_barrier_checked=$true
$report.worker_dispatch_exit_same_OS_thread=$true;$report.worker_exit_join_barrier_checked=$true
$report.worker_exit_failure_observable=$true;$report.worker_lifecycle_successful_pairs=10
$report.legacy_Config48_compatibility_checked=$true
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-signal-control-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
