param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/split-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-split-test.txt',$root)
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -encoding UTF-8 -g -proc:none -d $classes java/subset/dev/boom/split/SplitProgram.java java/reference/SplitReference.java
if($LASTEXITCODE -ne 0){throw 'Split fixture/reference javac failed'}
& $Boom compile-program --class-file (Join-Path $classes dev/boom/split/SplitProgram.class) --entry-class dev/boom/split/SplitProgram --method split --descriptor '(Ljava/lang/String;Ljava/lang/String;II)[Ljava/lang/String;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root program) --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 12;throw 'Split compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-split.py (Join-Path $root program/program.json) $JdkBase > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Split source binding proof failed'}
& D:/Dev/Python312/python.exe scripts/make-split-cases.py (Join-Path $root cases.txt) > (Join-Path $root case-count.txt)
if($LASTEXITCODE -ne 0){throw 'Split input generation failed'}
[string[]]$lines=Get-Content (Join-Path $root cases.txt)
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'SplitReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Split JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$jvm.StandardInput.Write(($lines -join "`n")+"`n");$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(60000)){$jvm.Kill($true);throw 'Split reference timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
$npe=@($p.object_layouts|Where-Object class_name -eq java/lang/NullPointerException)[0].class_id
Add-Type -Path tests/host/SplitProbe.cs
$actual=[BoomSplitProbe]::Run($p.compilation.dll,$lines,[uint32]$npe)
if($actual.Count -ne $expected.Count){throw 'Split differential record count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Split mismatch input=$($lines[$i]) expected=$($expected[$i]) actual=$($actual[$i])"}}
& D:/Dev/Python312/python.exe scripts/make-private-split.py $classes
if($LASTEXITCODE -ne 0){throw 'Private split fixture generation failed'}
$bad=Join-Path $root private-call
& $Boom compile-program --class-file (Join-Path $classes dev/boom/split/PrivateSplit.class) --entry-class dev/boom/split/PrivateSplit --method main --descriptor '([Ljava/lang/String;)V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $bad --assemble > (Join-Path $root private-aot.json) 2> (Join-Path $root private-aot.err)
if($LASTEXITCODE -eq 0 -or (Test-Path (Join-Path $bad program.json)) -or (Get-Content (Join-Path $root private-aot.err) -Raw) -notmatch 'Missing JDK bridge proof'){throw 'Private split accepted an application caller'}
& $inputs.java.executable -Xverify:all -cp $classes dev.boom.split.PrivateSplit > (Join-Path $root private-jvm.out) 2> (Join-Path $root private-jvm.err)
if($LASTEXITCODE -eq 0 -or (Get-Content (Join-Path $root private-jvm.err) -Raw) -notmatch 'IllegalAccessError'){throw 'JVM private split rejection differs'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Split compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;JVM_cases=$lines.Count;split_JVM_cases=12609;trim_JVM_cases=131079;trim_exhaustive_UTF16_units=65536;private_split_rejected_by_AOT_and_JVM=$true;original_public_wrappers_executed=$true;original_private_Java_methods_executed=$false;literal_fast_path=$true;regex_engine_complete=$false;unsupported_regex_fails_explicitly=$true;limits_empty_pieces_identity_delimiter_reuse_checked=$true;pending_context_preserved=$true;foreign_heap_wrong_type_bad_metadata_rejected=$true;parallel_workers=8;parallel_splits=2048;OOM_and_explicit_reclamation_checked=$true;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-split-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
