param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$Runtime='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/runtime-resource-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-runtime-resource-test.txt',$root)
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/processors/ProcessorProgram.java java/reference/ProcessorReference.java
if($LASTEXITCODE -ne 0){throw 'Runtime resource fixture/reference javac failed'}
$programs=@{}
foreach($method in @('count','memory','uncaught')){
 $descriptor=switch($method){count {'(I)I'};memory {'(I)J'};uncaught {'(Ljava/lang/Runtime;)I'}}
 & $Boom compile-program --entry-class dev/boom/processors/ProcessorProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --class-file (Join-Path $classes dev/boom/processors/ProcessorProgram.class) --output (Join-Path $root $method) --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
 if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 8;throw 'Runtime resource compilation failed'}
 & D:/Dev/Python312/python.exe scripts/verify-runtime-resources.py (Join-Path $root "$method/program.json") $JdkBase > (Join-Path $root ($method+'-source-contract.json'))
 if($LASTEXITCODE -ne 0){throw 'Runtime resource source proof failed'}
 $programs[$method]=Get-Content (Join-Path $root "$method/program.json") -Raw|ConvertFrom-Json
}
Add-Type -Path tests/host/ProcessorProbe.cs
$p=$programs.count;$state=@($p.classes|Where-Object name -eq java/lang/Runtime)[0];$field=@($state.fields|Where-Object name -eq currentRuntime)[0]
$cases=[BoomProcessorProbe]::Run($p.compilation.dll,'',$inputs.java.executable,$classes,[uint32]$state.id,[uint32]$field.index)
if($Runtime){$packaged=[BoomProcessorProbe]::Run($p.compilation.dll,(Resolve-Path $Runtime).Path,$inputs.java.executable,$classes,[uint32]$state.id,[uint32]$field.index);if($cases -ne $packaged){throw 'Packaged processor case count differs'}}
$p=$programs.memory;$state=@($p.classes|Where-Object name -eq java/lang/Runtime)[0];$field=@($state.fields|Where-Object name -eq currentRuntime)[0]
[BoomProcessorProbe]::Memory($p.compilation.dll,'',[uint32]$state.id,[uint32]$field.index)
if($Runtime){[BoomProcessorProbe]::Memory($p.compilation.dll,(Resolve-Path $Runtime).Path,[uint32]$state.id,[uint32]$field.index)}
$p=$programs.uncaught;$npe=@($p.exception_runtime.factories|Where-Object kind -eq 4)[0].class_id
[BoomProcessorProbe]::NullFailure($p.compilation.dll,[uint32]$npe,[uint32]$p.entry_id)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Runtime resource compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=3;processor_affinity_JVM_cases=$cases;source_native_declarations_verified=4;original_Runtime_getRuntime_initializer_and_constructor_executed=$true;Runtime_singleton_created_once=$true;full_runtime_tested=[bool]$Runtime;full_runtime_sha256=$(if($Runtime){(Get-FileHash $Runtime).Hash.ToLowerInvariant()}else{''});parallel_workers=8;parallel_cold_processor_calls=1024;parallel_allocation_and_memory_queries=1024;memory_values_match_actual_arena_and_occupied_spans=$true;memory_bytes_compared_to_JVM=$false;full_heap_resource_queries_zero_allocation=$true;Runtime_root_survives_explicit_collection=$true;pending_context_preserved=$true;null_wrong_type_foreign_heap_bad_policy_rejected=$true;actual_NPE_and_original_PC_checked=$true;processor_groups_greater_than_one_tested=$false;job_group_affinity_changed_by_test=$false;Runtime_override_dispatch_complete=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-runtime-resource-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
