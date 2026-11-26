param([string]$Boom='target/release/boom.exe',[string]$RunDirectory='',[switch]$SkipCompile,[string]$Runtime='.boom/assembly-runtime-v73-display/boom-runtime.dll')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $RunDirectory){$RunDirectory=Join-Path (Get-Location) ('.boom/constructor-tests/'+[guid]::NewGuid().ToString('N'))}
$root=[IO.Path]::GetFullPath($RunDirectory);[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-constructor-test.txt',$root)
$classes=Join-Path $root classes
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$modules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json
if(-not $SkipCompile){
 & D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -parameters -proc:none -d $classes java/subset/dev/boom/constructors/CtorProgram.java java/subset/dev/boom/constructors/OtherCaller.java java/subset/dev/boom/constructors/Counters.java java/reference/ConstructorReference.java
 if($LASTEXITCODE -ne 0){throw 'Constructor javac failed'}
 $arguments=@('compile-program','--entry-class','dev/boom/constructors/CtorProgram','--method','run','--descriptor','(II[Ljava/lang/Class;[Ljava/lang/Object;ZLjava/lang/reflect/Constructor;)Ljava/lang/Object;','--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--jdk-modules',$modules,'--output',(Join-Path $root program),'--assemble')
 foreach($file in Get-ChildItem -LiteralPath "$classes/dev/boom/constructors" -Filter '*.class'){$arguments+=@('--class-file',$file.FullName)}
 & $Boom @arguments > "$root/compile.json" 2> "$root/compile.err"
 if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 12;throw 'Constructor AOT failed'}
}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'ConstructorReference',[IO.Path]::GetFullPath('tests/constructor-cases.tsv'))){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Constructor JVM reference did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Constructor reference timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
[IO.File]::WriteAllLines("$root/jvm.txt",[string[]]$expected)
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
$plan=$p.reflected_constructors
& D:/Dev/Python312/python.exe scripts/verify-reflect-constructors.py "$root/program/program.json" $base $modules > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Constructor raw metadata/source verification failed'}
if(-not $plan -or $p.full_game_ready -or $plan.original_java_class_methods_executed -or $plan.original_java_constructor_methods_executed){throw 'Constructor validation scope differs'}
$names=[Collections.Generic.List[string]]::new();foreach($units in $plan.type_names){$names.Add([string]::new([char[]]$units))}
$ids=[Collections.Generic.List[uint32]]::new();$layouts=[Collections.Generic.List[string]]::new();$offsets=[Collections.Generic.List[uint32]]::new()
foreach($layout in $p.object_layouts){$ids.Add([uint32]$layout.class_id);$layouts.Add($layout.class_name.Replace('/','.'));$score=@($layout.layout.fields|Where-Object name -eq score);$offsets.Add($(if($score.Count){[uint32]$score[0].offset}else{[uint32]::MaxValue}))}
$boxOffsets=[uint32[]]@($plan.catalog.boxes|Sort-Object kind|ForEach-Object value_offset)
$cause=@(@($p.exception_runtime.factories|Where-Object kind -eq 27)[0].fields|Where-Object name -eq cause)[0].offset
$counter=@($p.classes|Where-Object name -eq dev/boom/constructors/Counters)[0];$field=@($counter.fields|Where-Object name -eq count)[0].index
Add-Type -Path tests/host/ConstructorProbe.cs
$actual=[BoomConstructorProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath('tests/constructor-cases.tsv'),$names.ToArray(),$ids.ToArray(),$layouts.ToArray(),$offsets.ToArray(),$boxOffsets,[uint32]$cause,[uint32]$counter.id,[uint32]$field)
[IO.File]::WriteAllLines("$root/native.txt",[string[]]$actual)
if($actual.Count -ne $expected.Count){throw "Constructor record count differs: $($actual.Count) / $($expected.Count)"}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Constructor mismatch expected=$($expected[$i]) actual=$($actual[$i])"}}
[BoomConstructorProbe]::Parallel($p.compilation.dll,$names.ToArray(),$ids.ToArray(),$layouts.ToArray(),$offsets.ToArray(),$boxOffsets,[uint32]$counter.id,[uint32]$field)
[BoomConstructorProbe]::Edges($p.compilation.dll,$names.ToArray(),$ids.ToArray(),$layouts.ToArray(),$offsets.ToArray(),$boxOffsets,[uint32]$cause)
if(-not (Test-Path -LiteralPath $Runtime)){throw 'Full Constructor runtime is required for this verification'}
$caller=@($plan.sites|Where-Object {$_.binding.operation -eq 'Invoke' -and $_.binding.caller.binary_name -eq 'dev.boom.constructors.CtorProgram'})[0].binding.caller_type
[BoomConstructorProbe]::Packaged($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),$names.ToArray(),$ids.ToArray(),$layouts.ToArray(),$offsets.ToArray(),$boxOffsets,[uint32]$cause,[uint32]$caller)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Constructor compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;full_runtime_tested_with_VM_site_fixture=$true;full_runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();JVM_cases=$expected.Count;original_target_Java_constructors_executed=$true;original_Java_Class_and_Constructor_API_wrappers_executed=$false;VM_owned_Constructor_representation=$true;lookup_does_not_initialize_target=$true;wide_17_parameter_constructor_checked=$true;private_nestmate_and_other_caller_access_checked=$true;primitive_unboxing_and_widening_checked=$true;constructor_Throwable_wrapping_and_initializer_failures_checked=$true;fresh_Constructor_and_type_arrays=$true;generic_metadata_retained_but_generic_APIs_incomplete=$true;exception_messages_compared_only_for_NoSuchMethodException=$true;parallel_workers=8;cold_constructions=1024;explicit_GC_preserves_reflection_graph=$true;pending_context_and_malformed_or_foreign_Constructor_rejected=$true;unlinked_constructor_fails_explicitly=$true;OOM_not_wrapped_and_explicit_recovery_checked=$true;automatic_gc=$false;setAccessible_supported=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-constructor-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
