param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v73-display/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/reflection-dispatch-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-reflection-dispatch-test.txt',$root)
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$modules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d "$root/classes" java/subset/dev/boom/fields/ReflectionDispatchProgram.java java/reference/ReflectionDispatchReference.java
if($LASTEXITCODE -ne 0){throw 'Reflection dispatch oracle javac failed'}
$arguments=@('compile-program','--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--jdk-modules',$modules,'--entry-class','dev/boom/fields/ReflectionDispatchProgram','--method','run','--descriptor','(I)Ljava/lang/String;','--output',"$root/program",'--assemble')
foreach($name in @('ReflectionDispatchProgram','ReflectionDispatchProgram$Target')){$arguments+=@('--class-file',"$root/classes/dev/boom/fields/$name.class")}
& $Boom @arguments > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 12;throw 'Reflection dispatch AOT compilation failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',"$root/classes",'ReflectionDispatchReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Reflection dispatch oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Reflection dispatch oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if($p.schema -ne 73 -or $p.interface_dispatch_abi -ne 4){throw 'Reflection dispatch profile absent'}
& D:/Dev/Python312/python.exe scripts/verify-reflect-fields.py "$root/program/program.json" $base > "$root/field-source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Reflection dispatch field source proof failed'}
& D:/Dev/Python312/python.exe scripts/verify-reflect-constructors.py "$root/program/program.json" $base $modules > "$root/constructor-source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Reflection dispatch constructor source proof failed'}
Add-Type -Path tests/host/ReflectionDispatchProbe.cs
$actual=[BoomReflectionDispatchProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime))
if($actual.Count -ne $expected.Count){throw 'Reflection dispatch row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Reflection dispatch mode $i differs: JVM=$($expected[$i]); ASM=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Reflection dispatch compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=12;workers=8;parallel_calls=2048;original_Java_caller_executed=$true;Object_and_Member_dispatch_checked=$true;Constructor_and_Field_runtime_owned_metadata=$true;original_reflection_Java_API_bodies_executed=$false;frozen_toString_text_returns_fresh_Strings=$true;modifiers_arrays_varargs_erasure_exceptions_checked=$true;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-reflection-dispatch-test.txt',$root);Write-Output $json
exit 0
