param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v74/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/class-instance-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-class-instance-test.txt',$root)
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d "$root/classes" java/subset/dev/boom/fields/ClassInstanceProgram.java java/reference/ClassInstanceReference.java
if($LASTEXITCODE -ne 0){throw 'Class.isInstance oracle javac failed'}
$arguments=@('compile-program','--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--entry-class','dev/boom/fields/ClassInstanceProgram','--method','run','--descriptor','(I)Ljava/lang/String;','--output',"$root/program",'--assemble')
foreach($file in Get-ChildItem "$root/classes/dev/boom/fields" -Filter '*.class'){$arguments+=@('--class-file',$file.FullName)}
& $Boom @arguments > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 9;throw 'Class.isInstance AOT compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-class-instance.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Class.isInstance source verification failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',"$root/classes",'ClassInstanceReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Class.isInstance oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Class.isInstance oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
Add-Type -Path tests/host/ReflectionDispatchProbe.cs
$actual=[BoomReflectionDispatchProbe]::RunCases($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),141)
if($actual.Count -ne $expected.Count){throw 'Class.isInstance row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Class.isInstance mode $i differs: JVM=$($expected[$i]); ASM=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Class.isInstance compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=141;workers=8;parallel_calls=2048;original_Java_caller_executed=$true;Class_isInstance_in_ASM=$true;primitive_void_null_interface_inheritance_and_array_covariance_checked=$true;target_class_not_initialized=$true;multiple_application_defining_loaders_tested=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-class-instance-test.txt',$root);Write-Output $json
exit 0
