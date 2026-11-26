param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/reflect-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-reflect-test.txt',$root)
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d $classes java/subset/dev/boom/reflect/ReflectProgram.java java/subset/dev/boom/reflect/OtherCaller.java java/subset/dev/boom/reflectforeign/ForeignCaller.java java/reference/ReflectReference.java
if($LASTEXITCODE -ne 0){throw 'Reflection fixture/reference javac failed'}
$modules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json
$arguments=@('compile-program','--entry-class','dev/boom/reflect/ReflectProgram','--method','run','--descriptor','(III)Ljava/lang/Object;','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--jdk-modules',$modules,'--output',(Join-Path $root program),'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes dev/boom) -Recurse -Filter '*.class'){$arguments+=@('--class-file',$file.FullName)}
& $Boom @arguments > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 10;throw 'Reflective constructor compilation failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'ReflectReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Reflection JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Reflection reference timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
& D:/Dev/Python312/python.exe scripts/verify-reflect-new.py (Join-Path $root program/program.json) $JdkBase $modules > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw "Reflection source/access proof failed"}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
$ids=[Collections.Generic.List[uint32]]::new();$names=[Collections.Generic.List[string]]::new();$offsets=[Collections.Generic.List[uint32]]::new()
foreach($layout in $p.object_layouts){$ids.Add([uint32]$layout.class_id);$names.Add($layout.class_name.Replace('/','.'));$field=@($layout.layout.fields|Where-Object name -eq value);$offsets.Add($(if($field.Count){[uint32]$field[0].offset}else{[uint32]0}))}
$cause=@($p.exception_runtime.factories|Where-Object kind -eq 24)[0].fields|Where-Object name -eq cause
$throwMethod=@($p.symbols|Where-Object {$_.class_name -eq 'dev/boom/reflect/ReflectProgram$Throws' -and $_.method -eq '<init>'})[0].id
Add-Type -Path tests/host/ReflectProbe.cs
$state=@($p.classes|Where-Object name -eq dev/boom/reflect/ReflectProgram)[0];$countField=@($state.fields|Where-Object name -eq initCount)[0].index
$stringType=0;for($i=0;$i -lt $p.mirror_types.Count;$i++){if($p.mirror_types[$i].key.name -eq "java/lang/String"){$stringType=$i;break}}
$actual=[BoomReflectProbe]::Run($p.compilation.dll,$ids.ToArray(),$names.ToArray(),$offsets.ToArray(),[uint32]$cause.offset,[uint32]$throwMethod,[uint32]$state.id,[uint32]$countField,[uint32]$stringType)
if($actual.Count -ne $expected.Count){throw 'Reflection differential record count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Reflection mismatch expected=$($expected[$i]) actual=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Reflection compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;JVM_cases=$expected.Count;original_Java_constructors_executed=$true;original_Java_Class_newInstance_executed=$false;Class_literals_do_not_initialize_target=$true;target_initializer_executes_exactly_once=$true;unlinked_constructor_fails_explicitly=$true;constructor_and_initializer_Throwable_chains_checked=$true;private_nestmate_package_and_cross_package_access_checked=$true;constructor_Throwable_identity_and_PC_preserved=$true;parallel_workers=8;parallel_cold_constructions=1024;pending_context_preserved=$true;foreign_heap_wrong_type_bad_metadata_rejected=$true;OOM_origin_and_explicit_reclamation_checked=$true;unlinked_constructor_rows=@($p.reflect_new.sites[0].rows|Where-Object action -eq 4).Count;dynamic_class_loading_complete=$false;exception_messages_compared=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-reflect-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
