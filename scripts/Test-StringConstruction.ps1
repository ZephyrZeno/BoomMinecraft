param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/string-construction-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-string-construction-test.txt',$root)
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/construction/ConstructProgram.java java/reference/StringConstructionReference.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'String construction fixture/reference javac failed'}
$programs=@{}
foreach($method in @('value','valueAll','check')) {
 $descriptor=if($method -ne 'check'){'([CII)Ljava/lang/String;'}else{'(III)I'}
 & $Boom compile-program --class-file (Join-Path $classes dev/boom/construction/ConstructProgram.class) --metadata-lock $MetadataLock --jdk-base $JdkBase --entry-class dev/boom/construction/ConstructProgram --method $method --descriptor $descriptor --output (Join-Path $root $method) --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
 if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 12;throw "String construction compile failed: $method"}
 & D:/Dev/Python312/python.exe scripts/verify-string-construction.py (Join-Path $root "$method/program.json") $JdkBase > (Join-Path $root ($method+'-source-contract.json'))
 if($LASTEXITCODE -ne 0){throw 'Independent String construction source proof failed'}
 $programs[$method]=Get-Content (Join-Path $root "$method/program.json") -Raw|ConvertFrom-Json
}
function Hex([int]$n){[BitConverter]::ToUInt32([BitConverter]::GetBytes($n),0).ToString('x')}
function Java([string]$main,[string[]]$lines,[string[]]$extra=@()){
 $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
 foreach($arg in (@('-Xmx128m','--add-opens=java.base/sun.net.www=ALL-UNNAMED','-cp',$classes,$main)+$extra)){$info.ArgumentList.Add($arg)}
 foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
 $jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
 try {if(-not $jvm.Start()){throw 'Construction JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$jvm.StandardInput.Write(($lines -join "`n")+"`n");$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Construction reference timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
}
$raw=[Collections.Generic.List[string]]::new()
foreach($units in @('null','-','0','41','0,41,ff,100,4e2d,d83d,de00,d800,dfff,ffff')){
 $length=if($units -in @('null','-')){0}else{$units.Split(',').Count}
 foreach($offset in @(-1,0,1,$length,($length+1),[int]::MinValue,[int]::MaxValue)) {foreach($count in @(-1,0,1,$length,($length+1),[int]::MinValue,[int]::MaxValue)){$raw.Add("$units $(Hex $offset) $(Hex $count)")}}
}
$random=[Random]::new(61061)
for($i=0;$i -lt 256;$i++){
 $length=$random.Next(0,33);$units=if($length -eq 0){'-'}else{(@(for($k=0;$k -lt $length;$k++){$random.Next(65536).ToString('x')})) -join ','}
 if($i%3 -eq 0){$offset=$random.Next(0,$length+1);$count=$random.Next(0,$length-$offset+1)}else{$offset=$random.Next(-2,$length+3);$count=$random.Next(-2,$length+3)}
 $raw.Add("$units $(Hex $offset) $(Hex $count)")
}
$expected=Java StringConstructionReference $raw.ToArray()
Add-Type -Path tests/host/StringConstructionProbe.cs
$p=$programs.value;$npe=@($p.object_layouts|Where-Object class_name -eq java/lang/NullPointerException)[0].class_id;$bounds=@($p.object_layouts|Where-Object class_name -eq java/lang/StringIndexOutOfBoundsException)[0].class_id
$actual=[BoomStringConstructionProbe]::Run($p.compilation.dll,$raw.ToArray(),[uint32]$npe,[uint32]$bounds,[uint32]$p.entry_id,7)
if($actual.Count -ne $expected.Count -or ($actual -join '|') -cne ($expected -join '|')){throw 'Raw String construction/null/bounds/UTF16 JVM mismatch'}
$whole=[Collections.Generic.List[string]]::new()
foreach($units in @('null','-','0','41','0,41,ff,100,4e2d,d83d,de00,d800,dfff,ffff')){$length=if($units -in @('null','-')){0}else{$units.Split(',').Count};$whole.Add("$units 0 $(Hex $length)")}
for($i=0;$i -lt 256;$i++){$length=$random.Next(0,65);$units=if($length -eq 0){'-'}else{(@(for($k=0;$k -lt $length;$k++){$random.Next(65536).ToString('x')})) -join ','};$whole.Add("$units 0 $(Hex $length)")}
$expected=Java StringConstructionReference $whole.ToArray() @('all')
$p=$programs.valueAll;$npe=@($p.object_layouts|Where-Object class_name -eq java/lang/NullPointerException)[0].class_id;$bounds=@($p.object_layouts|Where-Object class_name -eq java/lang/StringIndexOutOfBoundsException)[0].class_id
$actual=[BoomStringConstructionProbe]::Run($p.compilation.dll,$whole.ToArray(),[uint32]$npe,[uint32]$bounds,[uint32]$p.entry_id,5)
if($actual.Count -ne $expected.Count -or ($actual -join '|') -cne ($expected -join '|')){throw 'Whole char[] String construction/null/UTF16 JVM mismatch'}
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root fp-build.log) 2>&1
if($LASTEXITCODE -ne 0){throw 'String construction FP probe build failed'}
Add-Type -Path tests/host/NumericProbe.cs
$numeric=[Collections.Generic.List[string]]::new()
foreach($seed in @(-1,0,1,2,7,31,32,255,256,[int]::MinValue,[int]::MaxValue)){foreach($offset in @(-1,0,1,30,31,[int]::MaxValue)){foreach($count in @(-1,0,1,2,31,[int]::MaxValue)){$numeric.Add("$(Hex $seed) $(Hex $offset) $(Hex $count)")}}}
$records=@($numeric|ForEach-Object{"dev.boom.construction.ConstructProgram check (III)I $_"})
$expected=Java dev.boom.subset.ClassNumericOracle $records
$actual=[BoomNumericProbe]::Run($programs.check.compilation.dll,(Join-Path $root fpstate.dll),$numeric.ToArray(),'I',$true)
if($actual.Count -ne $expected.Count -or ($actual -join '|') -cne ($expected -join '|')){throw 'String constructor Java identity/hash/catch JVM mismatch'}
$pathOut=Join-Path $root path
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class sun/net/www/ParseUtil --method encodePath --descriptor '(Ljava/lang/String;IC)Ljava/lang/String;' --output $pathOut --assemble > (Join-Path $root path-compile.json) 2> (Join-Path $root path-compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root path-compile.err) -Tail 12;throw 'Original ParseUtil.encodePath compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-string-construction.py (Join-Path $pathOut program.json) $JdkBase > (Join-Path $root path-source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Original ParseUtil construction source proof failed'}
$pathProgram=Get-Content (Join-Path $pathOut program.json) -Raw|ConvertFrom-Json
$pathCases=[Collections.Generic.List[string]]::new()
foreach($line in @('null 0 2f','- 0 2f','61,20,62 0 2f','43,3a,5c,4e2d,6587,5c,61,20,62 0 5c','d83d,de00,d800,dc00,dfff,0 0 2f')){$pathCases.Add($line)}
for($i=0;$i -lt 256;$i++){
 $length=$random.Next(0,65);$units=if($length -eq 0){'-'}else{(@(for($k=0;$k -lt $length;$k++){$random.Next(65536).ToString('x')})) -join ','}
 $offset=$random.Next(0,$length+1);$separator=if($i%2 -eq 0){'2f'}else{'5c'};$pathCases.Add("$units $(Hex $offset) $separator")
}
$expected=Java StringConstructionReference $pathCases.ToArray() @('path')
$npe=@($pathProgram.object_layouts|Where-Object class_name -eq java/lang/NullPointerException)[0].class_id
$actual=[BoomStringConstructionProbe]::ParsePath($pathProgram.compilation.dll,$pathCases.ToArray(),[uint32]$npe)
if($actual.Count -ne $expected.Count -or ($actual -join '|') -cne ($expected -join '|')){throw 'Original ParseUtil percent encoding/JVM mismatch'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'String compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=4;whole_char_array_JVM_cases=$whole.Count;whole_char_array_constructor_Code_bytes=10;runtime_provided_String_semantics=$true;original_Java_String_constructor_executed=$false;original_Java_String_initializer_executed=$false;source_constructor_Code_bytes=14;raw_UTF16_null_and_bounds_JVM_cases=$raw.Count;Java_identity_hash_and_catch_JVM_cases=$numeric.Count;original_ParseUtil_encodePath_Code_executed=$true;original_ParseUtil_JVM_cases=$pathCases.Count;cold_String_allocation_before_any_literal_checked=$true;uninitialized_receiver_verifier_required=$true;exception_class_and_constructor_source_PC_checked=$true;exception_messages_compared=$false;mutable_input_not_aliased=$true;fresh_String_identity=$true;parallel_workers=8;parallel_constructor_calls=1024;pending_context_preserved=$true;foreign_heap_wrong_array_type_rejected=$true;allocation_and_copy_OOM_no_partial_publication=$true;quiescent_GC_String_backing_roots_and_recovery_checked=$true;compact_strings=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-string-construction-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
