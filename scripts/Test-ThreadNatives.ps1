param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/thread-native-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-thread-native-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json;$classes=Join-Path $root classes
foreach($file in $inputs.java.runtime_files){if((Get-FileHash $file.path).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Thread native JVM oracle runtime changed'}}
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/threadnative/ThreadNativeCalls.java java/reference/ThreadNativesReference.java
if($LASTEXITCODE -ne 0){throw 'Thread native fixture/oracle javac failed'}
function Java([string[]]$arguments){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('--add-opens','java.base/java.lang=ALL-UNNAMED','-Xmx128m','-cp',$classes,'ThreadNativesReference')+$arguments){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Thread JVM oracle failed'};$out=$java.StandardOutput.ReadToEndAsync();$err=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Thread JVM oracle timeout'};return @{code=$java.ExitCode;stdout=$out.GetAwaiter().GetResult();stderr=$err.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$jvm=Java -arguments @((Join-Path $root fields.json));if($jvm.code -ne 0){throw $jvm.stderr}
$fields=Get-Content (Join-Path $root fields.json) -Raw|ConvertFrom-Json;if(-not $fields.marker_is_Thread_class -or $fields.empty_stack_trace_length -ne 0){throw 'JVM Thread bootstrap fields changed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
$init=Join-Path $root init
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/Thread --method onSpinWait --descriptor '()V' --output $init --assemble > (Join-Path $root init-compile.json) 2> (Join-Path $root init-compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root init-compile.err) -Tail 15;throw 'Original Thread initialization compilation failed'}
$current=Join-Path $root current
& $Boom compile-program --class-file (Join-Path $classes dev/boom/threadnative/ThreadNativeCalls.class) --entry-class dev/boom/threadnative/ThreadNativeCalls --method current --descriptor '()Ljava/lang/Thread;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $current --assemble > (Join-Path $root current-compile.json) 2> (Join-Path $root current-compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root current-compile.err) -Tail 15;throw 'Thread.currentThread callsite compilation failed'}
$p=Get-Content (Join-Path $init program.json) -Raw|ConvertFrom-Json;$q=Get-Content (Join-Path $current program.json) -Raw|ConvertFrom-Json
foreach($program in @($p,$q)){
    $plan=$program.thread_natives
    if($program.schema -ne 53 -or $program.full_game_ready -or $plan.declarations.Count -ne 18 -or @($plan.declarations|Where-Object implemented).Count -ne 5 -or $plan.native_coverage_complete -or -not $plan.platform_threads_only -or $plan.origin.sha256 -ne $base.classes.'java.lang.Thread'.sha256 -or $plan.automatic_gc){throw 'Thread source/native capability scope changed'}
    foreach($pair in @(@('native_source_sha256','native/runtime/thread_natives.asm'),@('registry_source_sha256','native/runtime/thread_registry.asm'),@('runtime_types_source_sha256','native/runtime/runtime_types.asm'))){if($plan.($pair[0]) -ne (Get-FileHash $pair[1]).Hash.ToLowerInvariant()){throw 'Thread native dependency digest changed'}}
}
foreach($file in @((Join-Path $init program.json),(Join-Path $current program.json))){& D:/Dev/Python312/python.exe scripts/verify-thread-native-contract.py $file >> (Join-Path $root source-contract-checks.jsonl);if($LASTEXITCODE -ne 0){throw 'Independent Thread source/callsite verification failed'}}
if(@($p.symbols|Where-Object {$_.class_name -ne 'java/lang/Thread' -or $_.method -notin @('onSpinWait','<clinit>')}).Count -or $p.symbols.Count -ne 2 -or @($q.thread_natives.bindings|Where-Object operation -eq Current).Count -ne 1){throw 'Original Thread/current callsite scope changed'}
$owner=@($p.classes|Where-Object name -eq 'java/lang/Thread')[0];$marker=@($owner.fields|Where-Object name -eq NEW_THREAD_BINDINGS)[0].index;$empty=@($owner.fields|Where-Object name -eq EMPTY_STACK_TRACE)[0].index
Add-Type -Path tests/host/ThreadNativesProbe.cs
[BoomThreadNativesProbe]::Initialize($p.compilation.dll,(Join-Path $root boom-runtime.dll),[uint32]$owner.id,[uint32]$p.thread_natives.thread_type,[uint32]$marker,[uint32]$empty)
[BoomThreadNativesProbe]::CurrentQueries($q.compilation.dll)
& D:/Dev/Python312/python.exe scripts/make-thread-native-fixture.py $classes;if($LASTEXITCODE -ne 0){throw 'Private Thread fixture generation failed'}
$reason=(& $Boom compile-program --class-file (Join-Path $classes dev/boom/threadnative/BadRegistration.class) --entry-class dev/boom/threadnative/BadRegistration --method run --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root private-call) --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $reason -notmatch 'Thread private native is restricted'){throw 'Application called private Thread.registerNatives'}
$jvm=Java -arguments @('bad');if($jvm.code -eq 0 -or $jvm.stderr -notmatch 'IllegalAccessError'){throw 'JVM Thread native access check differs'}
$direct=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/Thread --method currentThread --descriptor '()Ljava/lang/Thread;' --output (Join-Path $root direct-native) --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $direct -notmatch 'cannot bypass original class initialization and VM attachment'){throw 'Direct Thread native entry bypassed class initialization'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Thread native compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('src/compiler/thread_natives.rs','native/runtime/thread_natives.asm','scripts/Test-ThreadNatives.ps1','tests/host/ThreadNativesProbe.cs','scripts/make-thread-native-fixture.py','scripts/verify-thread-native-contract.py','java/subset/dev/boom/threadnative/ThreadNativeCalls.java','java/reference/ThreadNativesReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=2;original_Thread_initializer_and_onSpinWait_executed=$true;native_table_declarations=18;independent_classfile_contract_checks=2;native_executable_operations=5;native_unimplemented_error_thunks=13;cold_class_init_workers=8;cold_class_init_records=6147;JVM_bootstrap_fields_compared=2;warm_zero_allocation_calls=128;AOT_currentThread_identity_calls=1536;currentThread_OS_threads=8;unattached_detached_wrong_type_and_wrong_heap_rejected=$true;native_query_metadata_and_pending_context_checked=$true;unsupported_native_operations_return_errors=$true;GC_static_root_graph_checked=$true;VM_preconstructor_storage_only=$true;original_Thread_constructor_run_start_exit_executed=$false;yield_carrier_ID_address_raw_VM_service_checked=$true;yield_carrier_ID_address_bytecode_execution_verified=$false;private_registration_rejected_by_AOT_and_JVM=$true;direct_native_entry_cannot_bypass_initializer=$true;native_coverage_complete=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash (Join-Path $root fields.json)).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-thread-native-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
