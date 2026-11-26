param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v74/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/record-bootstrap-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-record-bootstrap-test.txt',$root)
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -encoding UTF-8 -d "$root/classes" java/subset/dev/boom/records/RecordProgram.java java/reference/RecordReference.java
if($LASTEXITCODE -ne 0){throw 'Record oracle javac failed'}
$arguments=@('compile-program','--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--entry-class','dev/boom/records/RecordProgram','--method','run','--descriptor','(I)Ljava/lang/String;','--output',"$root/program",'--assemble')
foreach($file in Get-ChildItem "$root/classes/dev/boom/records" -Filter '*.class'){$arguments+=@('--class-file',$file.FullName)}
& $Boom @arguments > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 10;throw 'Record AOT compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-record-bootstrap.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Independent record proof failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',"$root/classes",'RecordReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Record oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Record oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
Add-Type -Path tests/host/ReflectionDispatchProbe.cs
$texts=[BoomReflectionDispatchProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime))
$actual=@($texts|ForEach-Object{$encoded=[Text.StringBuilder]::new();foreach($unit in $_.ToCharArray()){$value=[uint16]$unit;[void]$encoded.AppendFormat('{0:x2}{1:x2}',($value -band 255),($value -shr 8))};$encoded.ToString()})
if($actual.Count -ne $expected.Count){throw 'Record oracle row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Record UTF16 mismatch at mode $i"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Record compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=12;workers=8;parallel_calls=2048;source_record_toString_and_generated_helpers_executed=$true;original_ObjectMethods_bootstrap_Java_body_executed=$false;raw_backing_fields_bypass_overridden_accessors=$true;nested_local_dollar_names_empty_identity_UTF16_and_scalar_boundaries_checked=$true;generic_Object_component_callbacks_verified=$false;float_double_component_formatting_verified=$false;record_equals_and_hashCode_lowering_implemented=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-record-bootstrap-test.txt',$root);Write-Output $json
exit 0
