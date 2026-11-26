param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$PreparedRun='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
if($PreparedRun){$root=[IO.Path]::GetFullPath($PreparedRun)}else{$root=Join-Path (Get-Location) ('.boom/thread-run-tests/'+[guid]::NewGuid().ToString('N'))}
$classes=Join-Path $root classes
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
if(-not $PreparedRun){
    [IO.Directory]::CreateDirectory($classes)|Out-Null
    foreach($file in $inputs.java.runtime_files){if((Get-FileHash $file.path).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Thread run oracle JVM differs from lock'}}
    & (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/threadrun/RunTask.java java/subset/dev/boom/threadrun/RunCalls.java java/reference/ThreadRunReference.java
    if($LASTEXITCODE -ne 0){throw 'Thread run fixture javac failed'}
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-Xmx128m','-cp',$classes,'ThreadRunReference',(Join-Path $root oracle.bin))){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Thread run oracle failed to start'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Thread run oracle timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
    & scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/threadrun/RunCalls.class) --class-file (Join-Path $classes dev/boom/threadrun/RunTask.class) --entry-class dev/boom/threadrun/RunCalls --method apply --descriptor '(ILjava/lang/Thread;Ldev/boom/threadrun/RunTask;II)Ldev/boom/threadrun/RunTask;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root program) --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 10;throw 'Original Thread.run closure compilation failed'}
}
if((Get-Item (Join-Path $root oracle.bin)).Length -ne 12800){throw 'Thread run JVM oracle count differs'}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
if($p.schema -ne 53 -or $p.full_game_ready -or @($p.thread_natives.declarations|Where-Object implemented).Count -ne 5 -or @($p.thread_natives.bindings|Where-Object operation -eq Materialize).Count -ne 1){throw 'Thread run native capability scope differs'}
foreach($entry in @(@('java/lang/Thread','run'),@('java/lang/Thread','runWith'),@('java/lang/Thread','scopedValueBindings'),@('java/lang/ref/Reference','reachabilityFence'),@('java/lang/ref/Reference','<clinit>'),@('java/lang/ref/Reference$1','<init>'),@('jdk/internal/access/SharedSecrets','setJavaLangRefAccess'))){if(@($p.symbols|Where-Object {$_.class_name -eq $entry[0] -and $_.method -eq $entry[1]}).Count -ne 1){throw ('Original Thread run dependency missing: '+($entry -join '.'))}}
function Id($name){[uint32]@($p.classes|Where-Object name -eq $name)[0].id}
function Offset($owner,$name){[int]@(@($p.object_layouts|Where-Object class_name -eq $owner)[0].layout.fields|Where-Object name -eq $name)[0].offset}
[uint32[]]$ids=@((Id java/lang/Thread),(Id 'java/lang/Thread$FieldHolder'),(Id java/lang/ArithmeticException),(Id java/lang/ref/Reference),(Id jdk/internal/access/SharedSecrets))
[int[]]$offsets=@((Offset java/lang/Thread holder),(Offset java/lang/Thread scopedValueBindings),(Offset 'java/lang/Thread$FieldHolder' task))
foreach($name in 'value','divisor','sum','calls','failures','matched'){$offsets+=Offset dev/boom/threadrun/RunTask $name}
$shared=@($p.classes|Where-Object name -eq jdk/internal/access/SharedSecrets)[0]
$field=[uint32]@($shared.fields|Where-Object name -eq javaLangRefAccess)[0].index
Add-Type -Path tests/host/ThreadRunProbe.cs
[BoomThreadRunProbe]::Run($p.compilation.dll,(Join-Path $root boom-runtime.dll),(Join-Path $root oracle.bin),$ids,$offsets,$field)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Thread run compiler changed during verification'}
$sources=[ordered]@{}
foreach($path in @('src/compiler/thread_natives.rs','native/runtime/thread_natives.asm','scripts/Test-ThreadRun.ps1','tests/host/ThreadRunProbe.cs','java/subset/dev/boom/threadrun/RunTask.java','java/subset/dev/boom/threadrun/RunCalls.java','java/reference/ThreadRunReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$(if($PreparedRun){$null}else{$sha});runtime_language='assembly';compiled_entries=1;original_Thread_run_runWith_and_scoped_value_getter_executed=$true;original_Reference_initializer_constructor_and_reachabilityFence_executed=$true;Thread_native_materialization_callsite_executed=$true;JVM_cases=512;cold_Reference_initialization_workers=8;original_run_multicore_calls=6147;run_does_not_change_current_thread=$true;null_Runnable_returns_normally=$true;arithmetic_exception_propagation_and_catch_checked=$true;GC_static_and_VM_view_root_graph_checked=$true;materialization_null_owned_foreign_heap_and_pending_context_checked=$true;VM_preconstructor_Thread_and_FieldHolder_storage_only=$true;original_Thread_constructor_start_exit_executed=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;prepared_run_reused=[bool]$PreparedRun;oracle_sha256=(Get-FileHash (Join-Path $root oracle.bin)).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-thread-run-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
