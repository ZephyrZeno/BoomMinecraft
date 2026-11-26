param([string]$Boom='target/release/boom.exe')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/string-codepoint-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-codepoint-test.txt',$root)
$classes=Join-Path $root classes
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d $classes java/subset/dev/boom/codepoints/CodePointProgram.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Code point javac failed'}
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& $Boom compile-program --class-file "$classes/dev/boom/codepoints/CodePointProgram.class" --entry-class dev/boom/codepoints/CodePointProgram --method run --descriptor '(IIII)I' --metadata-lock .boom/locks/server.json --jdk-base $base --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 12;throw 'Code point compilation failed'}
& scripts/Build-FpProbe.ps1 -Output $root > "$root/fp.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'FP verification helper failed'}
$cases=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt 65536;$i++){$cases.Add($i.ToString('x')+' '+(($i*109+37)-band65535).ToString('x')+' 0 0')}
foreach($high in 0..1023){$cases.Add((0xd800+$high).ToString('x')+' '+(0xdc00+(($high*71)-band1023)).ToString('x')+' 0 0')}
$units=@(0,65,255,256,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,0xe000,65535)
foreach($a in $units){foreach($b in $units){foreach($index in @('80000000','ffffffff','0','1','2','7fffffff')){$cases.Add($a.ToString('x')+' '+$b.ToString('x')+' '+$index+' 0')}}}
foreach($index in @('80000000','ffffffff','0','1','2','7fffffff')){$cases.Add('d800 dc00 '+$index+' 1')}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.RedirectStandardInput=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Code point JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$lines=@($cases|ForEach-Object{'dev.boom.codepoints.CodePointProgram run (IIII)I '+$_});if(-not $jvm.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(30000)){throw 'JVM code point input timeout'};$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Code point JVM timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{if(-not $jvm.HasExited){$jvm.Kill($true)};$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if($p.full_game_ready -or -not @($p.string_case.bindings|Where-Object name -eq codePointAt).Count){throw 'Code point source binding missing'}
Add-Type -Path tests/host/NumericProbe.cs
$actual=[BoomNumericProbe]::Run($p.compilation.dll,"$root/fpstate.dll",$cases.ToArray(),'I',$true)
if($expected.Count -ne $actual.Count){throw 'Code point case count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Code point mismatch $($cases[$i]) expected=$($expected[$i]) actual=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Code point compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;JVM_cases=$cases.Count;native_executions=$cases.Count*2;all_first_UTF16_units_checked=$true;all_high_surrogates_with_valid_low_surrogate_checked=$true;unpaired_surrogates_and_second_unit_indices_checked=$true;negative_and_extreme_indices_and_null_receiver_checked=$true;original_Java_String_codePointAt_executed=$false;source_declaration_bound=$true;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-codepoint-test.txt',$root);Write-Output $json
exit 0
