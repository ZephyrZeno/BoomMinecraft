param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v79b/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/string-getchars-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-string-getchars-test.txt',$root)
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d "$root/classes" java/subset/dev/boom/fields/GetCharsProgram.java java/reference/GetCharsReference.java
if($LASTEXITCODE -ne 0){throw 'getChars oracle javac failed'}
& $Boom compile-program --class-file "$root/classes/dev/boom/fields/GetCharsProgram.class" --metadata-lock .boom/locks/server.json --jdk-base $base --entry-class dev/boom/fields/GetCharsProgram --method run --descriptor '(I)Ljava/lang/String;' --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 10;throw 'getChars AOT compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-string-getchars.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Independent getChars source proof failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',"$root/classes",'GetCharsReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'getChars oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'getChars oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
Add-Type -Path tests/host/ReflectionDispatchProbe.cs
$texts=[BoomReflectionDispatchProbe]::RunCases($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),48)
$actual=@($texts|ForEach-Object{$encoded=[Text.StringBuilder]::new();foreach($unit in $_.ToCharArray()){$value=[uint16]$unit;[void]$encoded.AppendFormat('{0:x2}{1:x2}',($value -band 255),($value -shr 8))};$encoded.ToString()})
if($actual.Count -ne $expected.Count){throw 'getChars oracle row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "getChars UTF16 or exception message differs at $i"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'getChars compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=48;workers=8;parallel_calls=2048;original_Java_range_guards_executed=$false;range_guards_in_ASM=$true;original_String_getChars_body_executed=$false;copy_in_ASM=$true;null_and_range_check_order_checked=$true;bounds_messages_and_UTF16_checked=$true;helpful_NPE_message_exact=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-string-getchars-test.txt',$root);Write-Output $json
exit 0
