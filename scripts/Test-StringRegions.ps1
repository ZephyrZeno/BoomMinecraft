param([string]$Boom='target/release/boom.exe')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/string-region-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-region-test.txt',$root)
$classes=Join-Path $root classes
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d $classes java/subset/dev/boom/regions/RegionProgram.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'String region javac failed'}
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& $Boom compile-program --class-file "$classes/dev/boom/regions/RegionProgram.class" --entry-class dev/boom/regions/RegionProgram --method run --descriptor '(IIIIII)I' --metadata-lock .boom/locks/server.json --jdk-base $base --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 12;throw 'String region compilation failed'}
& scripts/Build-FpProbe.ps1 -Output $root > "$root/fp.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'FP verification helper failed'}
$cases=[Collections.Generic.List[string]]::new()
function Bits([int]$value){([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
foreach($a in 0..15){foreach($b in 0..15){foreach($x in @(-1,0,1,2,3,7,[int]::MaxValue)){foreach($y in @(-1,0,1,2,3,7,[int]::MaxValue)){foreach($length in @([int]::MinValue,-1,0,1,2,3,[int]::MaxValue)){foreach($mode in 0,2,3){$cases.Add($a.ToString('x')+' '+$b.ToString('x')+' '+(Bits $x)+' '+(Bits $y)+' '+(Bits $length)+' '+$mode.ToString('x'))}}}}}}
foreach($mode in 4,6,7,8,10,11,12,14,15){foreach($x in @([int]::MinValue,-1,0,1,2,3,[int]::MaxValue)){foreach($y in @([int]::MinValue,-1,0,1,2,3,[int]::MaxValue)){foreach($length in @([int]::MinValue,-1,0,1,2,3,[int]::MaxValue)){$cases.Add('1 2 '+(Bits $x)+' '+(Bits $y)+' '+(Bits $length)+' '+$mode.ToString('x'))}}}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.RedirectStandardInput=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'String region JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$lines=@($cases|ForEach-Object{'dev.boom.regions.RegionProgram run (IIIIII)I '+$_});if(-not $jvm.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(60000)){throw 'JVM String region input timeout'};$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(60000)){$jvm.Kill($true);throw 'String region JVM timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{if(-not $jvm.HasExited){$jvm.Kill($true)};$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if($p.full_game_ready -or -not @($p.string_case.bindings|Where-Object name -eq regionMatches).Count){throw 'String region source binding missing'}
Add-Type -Path tests/host/NumericProbe.cs
$actual=[BoomNumericProbe]::Run($p.compilation.dll,"$root/fpstate.dll",$cases.ToArray(),'I',$true)
if($expected.Count -ne $actual.Count){throw 'String region case count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "String region mismatch $($cases[$i]) expected=$($expected[$i]) actual=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'String region compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;JVM_cases=$cases.Count;native_executions=$cases.Count*2;both_regionMatches_overloads_checked=$true;Unicode_case_and_surrogate_region_boundaries_checked=$true;negative_lengths_long_arithmetic_and_extreme_indices_checked=$true;null_and_short_circuit_order_checked=$true;original_Java_String_regionMatches_executed=$false;source_declaration_bound=$true;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-region-test.txt',$root);Write-Output $json
exit 0
