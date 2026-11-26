param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v69/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/literal-regex-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-literal-regex-test.txt',$root)
$classes=Join-Path $root classes
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d $classes java/subset/dev/boom/literalregex/LiteralProgram.java java/subset/dev/boom/literalregex/Wide.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Literal regex javac failed'}
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& $Boom compile-program --class-file "$classes/dev/boom/literalregex/LiteralProgram.class" --class-file "$classes/dev/boom/literalregex/Wide.class" --entry-class dev/boom/literalregex/LiteralProgram --method run --descriptor '(III)I' --metadata-lock .boom/locks/server.json --jdk-base $base --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 12;throw 'Literal regex compilation failed'}
& scripts/Build-FpProbe.ps1 -Output $root > "$root/fp.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'FP verification helper failed'}
$cases=[Collections.Generic.List[string]]::new()
foreach($a in 0..15){foreach($route in 0..8){foreach($operation in 0..2){$cases.Add($a.ToString('x')+' '+$route.ToString('x')+' '+$operation.ToString('x'))}}}
foreach($a in 0..65535){$cases.Add($a.ToString('x')+' '+($a%9).ToString('x')+' 3')}
foreach($route in 0..8){foreach($operation in 0..2){$cases.Add('ffffffff '+$route.ToString('x')+' '+$operation.ToString('x'))}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.RedirectStandardInput=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Literal regex JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$lines=@($cases|ForEach-Object{'dev.boom.literalregex.LiteralProgram run (III)I '+$_});if(-not $jvm.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(30000)){throw 'JVM literal regex input timeout'};$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Literal regex JVM timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{if(-not $jvm.HasExited){$jvm.Kill($true)};$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if($p.schema -ne 69 -or $p.full_game_ready -or $p.literal_regex_replacements.Count -ne 9){throw 'Literal regex proof count/schema differs'}
Add-Type -Path tests/host/NumericProbe.cs
$actual=[BoomNumericProbe]::Run($p.compilation.dll,"$root/fpstate.dll",$cases.ToArray(),'I',$true)
if($expected.Count -ne $actual.Count){throw 'Literal regex case count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Literal regex mismatch $($cases[$i]) expected=$($expected[$i]) actual=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Literal regex compiler changed during verification'}
$rejections=@(foreach($name in @('badMeta','badIdentity','badSurrogate','badReplacement','badEmpty','badDynamic','badBranch')){
 $out=Join-Path $root ('reject-'+$name)
 & $Boom compile-program --class-file "$classes/dev/boom/literalregex/LiteralProgram.class" --class-file "$classes/dev/boom/literalregex/Wide.class" --entry-class dev/boom/literalregex/LiteralProgram --method $name --metadata-lock .boom/locks/server.json --jdk-base $base --output $out --assemble > "$root/$name.json" 2> "$root/$name.err"
 if($LASTEXITCODE -eq 0 -or (Test-Path "$out/program.json")){throw "Unproven regex optimization accepted: $name"}
 $errorText=Get-Content "$root/$name.err" -Raw;if($errorText -notmatch 'replaceAll'){throw "Unexpected rejection: $errorText"}
 $name
})
& D:/Dev/Python312/python.exe scripts/verify-literal-regex.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Literal regex source/control-flow proof failed'}
Add-Type -Path tests/host/LiteralRegexProbe.cs
[BoomLiteralRegexProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime))
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;full_runtime_tested=$true;full_runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();full_heap_no_match_calls=1024;pending_context_null_and_OOM_recovery_checked=$true;JVM_cases=$cases.Count;native_executions=$cases.Count*2;source_and_result_identity_compared=$true;all_UTF16_input_units_checked=$true;ldc_and_ldc_w_operands_checked=$true;literal_single_character_only=$true;unproven_regex_calls_rejected=$rejections;original_replaceAll_Java_wrapper_executed=$false;general_regex_engine_complete=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-literal-regex-test.txt',$root);Write-Output $json
exit 0
