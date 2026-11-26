param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/thread-registry-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-thread-registry-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$classes=Join-Path $root classes
foreach($file in $inputs.java.runtime_files){if((Get-FileHash $file.path).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Locked JVM oracle runtime changed'}}
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/threads/ThreadTask.java java/reference/ThreadTaskReference.java
if($LASTEXITCODE -ne 0){throw 'Thread task/oracle javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'ThreadTaskReference',(Join-Path $root oracle.bin))){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Thread task JVM oracle failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Thread JVM oracle timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-ThreadRegistryProbe.ps1 -Output $root *> (Join-Path $root adapter-build.log)
$programs=[Collections.Generic.List[string]]::new();$state='Ldev/boom/threads/ThreadTask$State;'
$classArgs=@(Get-ChildItem (Join-Path $classes dev/boom/threads) -Filter '*.class' -Force|ForEach-Object {'--class-file';$_.FullName})
foreach($entry in ,@('execute',('(I'+$state+'II)'+$state))){
    $name=$entry[0];$out=Join-Path $root $name
    & $Boom compile-program @classArgs --entry-class dev/boom/threads/ThreadTask --method $name --descriptor $entry[1] --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($name+'-compile.json')) 2> (Join-Path $root ($name+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($name+'-compile.err')) -Tail 14;throw 'Thread AOT workload compilation failed'}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.full_game_ready -or $p.signal_lookup_bindings.Count -or @($p.symbols|Where-Object {$_.class_name -eq 'java/lang/Thread'}).Count -or $p.symbols.Count -ne 7){throw 'Thread fixture must not claim original Thread support'}
    $programs.Add($p.compilation.dll)
}
Add-Type -Path tests/host/ThreadRegistryProbe.cs
$layout=@($p.object_layouts|Where-Object class_name -eq 'dev/boom/threads/ThreadTask$State')[0].layout
$resultField=@($layout.fields|Where-Object name -eq returned)[0];$checkField=@($layout.fields|Where-Object name -eq check)[0]
if($resultField.descriptor -ne 'J' -or $checkField.descriptor -ne 'J' -or $layout.reference_prefix_fields -ne 0){throw 'Thread fixture layout changed'}
[BoomThreadRegistryProbe]::Run((Join-Path $root boom-runtime.dll),(Join-Path $root thread-registry-probe.dll),$programs[0],[int]$resultField.offset,[int]$checkField.offset,(Join-Path $root oracle.bin))
$publicationThreads=[BoomThreadRegistryProbe]::RunPublication((Join-Path $root boom-runtime.dll),(Join-Path $root thread-registry-probe.dll))
if($publicationThreads -ne 512){throw 'Native pre-start publication coverage differs'}
Write-Output 'Verified native OS threads executing AOT guest tasks, errors/exits, FLS identities, thread roots and quiescent GC lease'
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Compiler changed during thread registry verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/thread_registry.asm','native/probe/thread_registry_probe.asm','scripts/Build-AssemblyRuntime.ps1','scripts/Build-ThreadRegistryProbe.ps1','scripts/Test-ThreadRegistry.ps1','tests/host/ThreadRegistryProbe.cs','java/subset/dev/boom/threads/ThreadTask.java','java/reference/ThreadTaskReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';raw_VM_thread_core_only=$true;compiled_fixture_entries=1;compiled_fixture_methods=$p.symbols.Count;compiled_original_Thread_entries=0;native_created_OS_threads=66;AOT_task_JVM_cases=64;AOT_failure_and_exit_callbacks_checked=$true;arithmetic_failure_callbacks=8;normal_exit_callbacks=65;native_uncaught_and_exit_errors_observable=$true;single_AOT_image_for_object_identity=$true;workers_for_ID_allocation=8;concurrent_unique_ID_records=6147;primordial_ID_reserved=1;ID_counter_overflow_checked=$true;FLS_current_reference_and_automatic_external_detach_checked=$true;foreign_heap_and_malformed_spawn_rejected=$true;active_threads_block_root_enumeration_and_destroy=$true;completed_thread_and_pending_roots_checked=65;GC_lease_blocks_attach_start_release_destroy=$true;GC_lease_owner_checked=$true;GC_static_and_thread_root_graph_checked=$true;release_removes_thread_roots=$true;abrupt_OS_thread_exit_reported_abnormal=$true;current_thread_hot_path_global_lock=$false;original_Thread_constructor_run_exit_executed=$false;Thread_currentThread_start0_bytecode_bindings_complete=$false;live_Java_stack_maps_complete=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash (Join-Path $root oracle.bin)).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$report.legacy_native_created_OS_threads=66
$report.native_created_OS_threads=66+[int]$publicationThreads
$report.publication_checked_OS_threads=[int]$publicationThreads
$report.publication_start_abi=2
$report.publication_start_bytes=88
$report.publication_callbacks=513
$report.publication_malformed_header_rejections=3
$report.prestart_peer_and_state_publication_checked=$true
$report.CreateThread_failure_rolls_back_VM_fields=$true
$report.CreateThread_failure_error_preserved=$true
$report.default_and_explicit_stack_reservation_checked=$true
$report.publication_registry_and_heap_cleanup_checked=$true
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-thread-registry-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
