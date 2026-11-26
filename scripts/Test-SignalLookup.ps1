param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$JdkModules='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
if(-not $JdkModules){$JdkModules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json}
$root=Join-Path (Get-Location) ('.boom/signal-lookup-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-signal-lookup-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/signals/SignalNames.java java/reference/SignalNamesReference.java
if($LASTEXITCODE -ne 0){throw 'Signal String producer/oracle javac failed'}
function Java([string[]]$arguments){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('--add-opens','java.base/jdk.internal.misc=ALL-UNNAMED','--add-exports','java.base/jdk.internal.misc=ALL-UNNAMED','-Xmx128m','-cp',$classes,'SignalNamesReference')+$arguments){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Signal JVM oracle failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(120000)){throw 'Signal JVM oracle timed out'};return @{code=$java.ExitCode;stdout=$stdout.GetAwaiter().GetResult();stderr=$stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$raw=Join-Path $root raw.bin;$literals=Join-Path $root literals.bin;$jvm=Java -arguments @($raw,$literals);if($jvm.code -ne 0){throw $jvm.stderr}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-SignalProbe.ps1 -Output $root *> (Join-Path $root signal-probe-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/SignalLookupProbe.cs
$programs=@{}
foreach($method in @('literal','raw')){
    $out=Join-Path $root $method
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/signals/SignalNames.class) --entry-class dev/boom/signals/SignalNames --method $method --descriptor '(I)Ljava/lang/String;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 14;throw 'Signal String producer compilation failed'}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 47 -or $p.signal_lookup_bindings.Count -or $p.full_game_ready -or $p.string_prefix.Count -eq 0){throw 'Raw signal test must remain a String producer without Java Signal invocation'}
    $programs[$method]=$p
}
$inspect=Join-Path $root contract
& $Boom inspect-signal-runtime --lock $MetadataLock --jdk-base $JdkBase --output $inspect > (Join-Path $root contract-inspect.json);if($LASTEXITCODE -ne 0){throw 'Signal source inspection failed'}
& D:/Dev/Python312/python.exe scripts/verify-signal-contract.py (Join-Path $inspect inspection.json) > (Join-Path $root contract-raw-check.json);if($LASTEXITCODE -ne 0){throw 'Independent Signal declaration/initializer verification failed'}
$contract=(Get-Content (Join-Path $inspect inspection.json) -Raw|ConvertFrom-Json).contract
if($contract.origin.sha256 -ne $base.classes.'jdk.internal.misc.Signal'.sha256 -or $contract.handler_registration_implemented -or $contract.storage_abi -ne 3){throw 'Original Signal contract changed'}
foreach($pair in @(@('native_source_sha256','native/runtime/signals.asm'),@('string_source_sha256','native/runtime/strings.asm'),@('heap_source_sha256','native/runtime/heap.asm'))){if($contract.($pair[0]) -ne (Get-FileHash $pair[1]).Hash.ToLowerInvariant()){throw 'Signal runtime contract hash changed'}}
[byte[]]$expected=[IO.File]::ReadAllBytes($raw);if($expected.Length -ne 524288){throw 'Raw signal oracle size changed'}
[BoomSignalLookupProbe]::Raw($programs.raw.compilation.dll,(Join-Path $root boom-runtime.dll),$expected)
Write-Output 'Validated 524288 raw UTF16 signal-name queries against the locked Windows JVM'
$bytes=[IO.File]::ReadAllBytes($literals);if($bytes.Length -ne 256){throw 'Signal literal oracle size changed'}
[int[]]$values=@(for($i=0;$i -lt 32;$i++){[BitConverter]::ToInt32([byte[]]@($bytes[$i*8+3],$bytes[$i*8+2],$bytes[$i*8+1],$bytes[$i*8]),0)})
[uint[]]$kinds=@(for($i=0;$i -lt 32;$i++){[BitConverter]::ToUInt32([byte[]]@($bytes[$i*8+7],$bytes[$i*8+6],$bytes[$i*8+5],$bytes[$i*8+4]),0)})
[BoomSignalLookupProbe]::Literals($programs.literal.compilation.dll,(Join-Path $root boom-runtime.dll),(Join-Path $root signal-jobs.dll),(Join-Path $root fpstate.dll),$values,$kinds)
[BoomSignalLookupProbe]::EmptyBoundary($programs.literal.compilation.dll,(Join-Path $root boom-runtime.dll))
& D:/Dev/Python312/python.exe scripts/make-signal-fixture.py $classes;if($LASTEXITCODE -ne 0){throw 'Signal private fixture generation failed'}
$bad=Join-Path $root private-call;$reason=(& $Boom compile-program --class-file (Join-Path $classes dev/boom/signals/BadLookup.class) --entry-class dev/boom/signals/BadLookup --method run --descriptor '()I' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $bad --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $reason -notmatch 'Signal.findSignal0 is private' -or (Test-Path (Join-Path $bad program.json))){throw 'Private signal native accepted an application caller'}
$jvm=Java -arguments @('bad','dev.boom.signals.BadLookup');if($jvm.code -eq 0 -or $jvm.stderr -notmatch 'IllegalAccessError'){throw 'JVM private native rejection differs'}
[IO.File]::WriteAllText((Join-Path $root private-aot.txt),$reason);[IO.File]::WriteAllText((Join-Path $root private-jvm.txt),$jvm.stderr)
$direct=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class jdk/internal/misc/Signal --method findSignal0 --descriptor '(Ljava/lang/String;)I' --output (Join-Path $root direct-native) --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $direct -notmatch 'cannot bypass original Signal class initialization'){throw 'Native entry bypassed Signal initialization'}
$phase=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --jdk-modules $JdkModules --entry-class java/lang/System --method initPhase1 --descriptor '()V' --output (Join-Path $root phase1) --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $phase -notmatch 'Linking locked jdk/internal/misc/Signal.handle0' -or $phase -notmatch 'requires its own assembly runtime binding'){throw 'Original System phase-one signal frontier changed; inspect before recording'}
[IO.File]::WriteAllText((Join-Path $root phase1-frontier.txt),$phase)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Signal compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('src/compiler/signals.rs','native/runtime/signals.asm','native/probe/signal_jobs.asm','scripts/Build-SignalProbe.ps1','scripts/Test-SignalLookup.ps1','scripts/verify-signal-contract.py','scripts/verify-jdk-bridges.py','scripts/make-signal-fixture.py','tests/host/SignalLookupProbe.cs','java/subset/dev/boom/signals/SignalNames.java','java/reference/SignalNamesReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_String_producers=2;compiled_Signal_Java_entries=0;raw_VM_service_only=$true;source_native_declarations_verified=3;original_initializer_Code_hash_verified=$true;original_private_constructor_callsite_verified=$true;Windows_signal_labels=7;raw_UTF16_JVM_cases=524288;literal_JVM_cases=32;literal_native_FP_calls=64;all_UTF16_units_in_eight_name_shapes=$true;case_sensitive_prefix_NUL_and_surrogate_cases=$true;native_lookup_null_exception_kind_checked=$true;native_null_exception_message_complete=$false;native_lookup_bytecode_binding_execution_verified=$false;full_heap_no_allocation_calls=8193;workers=8;multicore_records=6147;lookup_worker_guest_allocations=0;GC_static_root_graph_checked=$true;metadata_foreign_heap_corrupt_backing_and_pending_context_checked=$true;empty_backing_at_heap_end_and_guard_page=$true;private_call_rejected_by_AOT_and_JVM=$true;direct_native_entry_cannot_skip_initializer=$true;Signal_Java_initializer_executed=$false;signal_handlers_installed=$false;signal_handler_dispatch_complete=$false;phase1_frontier=$phase;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;raw_oracle_sha256=(Get-FileHash $raw).Hash.ToLowerInvariant();literal_oracle_sha256=(Get-FileHash $literals).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-signal-lookup-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
