param([string]$Boom='target/release/boom.exe',[string]$Method='run',[string]$Runtime='.boom/assembly-runtime-v70/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/sequence-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText(('.boom/current-sequence-'+$Method+'-test.txt'),$root)
$classes=Join-Path $root classes
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d $classes java/subset/dev/boom/sequence/SequenceProgram.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'String sequence javac failed'}
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$compileInputs=@();foreach($file in Get-ChildItem -LiteralPath "$classes/dev/boom/sequence" -Filter '*.class'){$compileInputs+=@('--class-file',$file.FullName)}
& $Boom compile-program @compileInputs --entry-class dev/boom/sequence/SequenceProgram --method $Method --descriptor '(IIII)I' --metadata-lock .boom/locks/server.json --jdk-base $base --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 12;throw 'String sequence compilation failed'}
& scripts/Build-FpProbe.ps1 -Output $root > "$root/fp.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'FP verification helper failed'}
$cases=[Collections.Generic.List[string]]::new()
function Bits([int]$value){([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
if($Method -eq 'run'){
 foreach($a in 0..13){foreach($t in 0..13){foreach($r in 0..13){foreach($oper in 0..3){foreach($kind in 0,1,8,9){$mode=$kind+($oper*64);$cases.Add($a.ToString('x')+' '+$t.ToString('x')+' '+$r.ToString('x')+' '+$mode.ToString('x'))}}}}}
 foreach($a in -1,0,1,5,7,9,12){foreach($t in 0..4){foreach($r in 0..4){foreach($oper in 0..3){$mode=$t+$r*8+$oper*64;$cases.Add((Bits $a)+' 3 2 '+$mode.ToString('x'))}}}}
 foreach($a in 0..13){foreach($t in 0..13){foreach($oper in 0..3){$mode=265+$oper*64;$cases.Add($a.ToString('x')+' '+$t.ToString('x')+' 0 '+$mode.ToString('x'))}}}
}else{
 for($i=0;$i -lt 65536;$i++){$cases.Add($i.ToString('x')+' '+(($i*109+37)-band65535).ToString('x')+' '+$i.ToString('x')+' '+(($i*71+23)-band65535).ToString('x'))}
}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.RedirectStandardInput=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'String sequence JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$lines=@($cases|ForEach-Object{'dev.boom.sequence.SequenceProgram '+$Method+' (IIII)I '+$_});if(-not $jvm.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(60000)){throw 'JVM String sequence input timeout'};$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(60000)){$jvm.Kill($true);throw 'String sequence JVM timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{if(-not $jvm.HasExited){$jvm.Kill($true)};$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if($p.schema -ne 70 -or $p.full_game_ready -or -not @($p.string_join_plans|Where-Object kind -eq Replace).Count){throw 'String sequence plan missing'}
Add-Type -Path tests/host/NumericProbe.cs
$actual=[BoomNumericProbe]::Run($p.compilation.dll,"$root/fpstate.dll",$cases.ToArray(),'I',$true)
if($expected.Count -ne $actual.Count){throw 'String sequence case count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "String sequence mismatch $($cases[$i]) expected=$($expected[$i]) actual=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'String sequence compiler changed during verification'}
& D:/Dev/Python312/python.exe scripts/verify-sequence-replace.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Sequence source/callback proof failed'}
if($Method -eq 'run'){
 Add-Type -Path tests/host/SequenceReplaceProbe.cs
 $seq=@($p.object_layouts|Where-Object class_name -eq 'dev/boom/sequence/SequenceProgram$Seq')[0]
 $marker=@($p.object_layouts|Where-Object class_name -eq 'dev/boom/sequence/SequenceProgram$Marker')[0]
 $owner=@($p.classes|Where-Object name -eq dev/boom/sequence/SequenceProgram)[0]
 $toString=@($p.symbols|Where-Object {$_.class_name -eq 'dev/boom/sequence/SequenceProgram$Seq' -and $_.method -eq 'toString'})[0]
 $value=@($seq.layout.fields|Where-Object name -eq value)[0].offset;$id=@($seq.layout.fields|Where-Object name -eq id)[0].offset;$mode=@($seq.layout.fields|Where-Object name -eq mode)[0].offset
 $trace=@($owner.fields|Where-Object name -eq trace)[0].index;$plan=@($p.string_join_plans|Where-Object kind -eq Replace)[0].id
 [BoomSequenceReplaceProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),[uint32]$plan,[uint32]$seq.class_id,[uint32]$value,[uint32]$id,[uint32]$mode,[uint32]$owner.id,[uint32]$trace,[uint32]$marker.class_id,[uint32]$toString.id)
}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;full_runtime_tested=($Method -eq 'run');full_runtime_sha256=$(if($Method -eq 'run'){(Get-FileHash $Runtime).Hash.ToLowerInvariant()}else{$null});VM_object_fixtures_used_for_full_runtime=($Method -eq 'run');parallel_workers=$(if($Method -eq 'run'){8}else{0});full_heap_no_match_calls=$(if($Method -eq 'run'){1024}else{0});method=$Method;JVM_cases=$cases.Count;native_executions=$cases.Count*2;custom_CharSequence_toString_order_and_exceptions_checked=($Method -eq 'run');content_hash_length_and_identity_checked=($Method -eq 'run');all_UTF16_input_units_checked=($Method -eq 'raw');original_Java_String_replace_CharSequence_body_executed=$false;callbacks_execute_original_Java_as_AOT_assembly=$true;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText(('.boom/latest-sequence-'+$Method+'-test.txt'),$root);Write-Output $json
exit 0
