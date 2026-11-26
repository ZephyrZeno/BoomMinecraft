param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/word-context-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-word-context-test.txt',$root)
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& $Boom inspect-word-break --lock $MetadataLock --jdk-base $JdkBase --output $root > (Join-Path $root prepare.json) 2> (Join-Path $root prepare.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root prepare.err) -Tail 10;throw 'Word context data preparation failed'}
$p=Get-Content (Join-Path $root word-plan.json) -Raw|ConvertFrom-Json
& scripts/Build-AssemblyRuntime.ps1 -Output $root -WordPlan (Join-Path $root word-plan.asm) > (Join-Path $root runtime-build.log) 2>&1
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root runtime-build.log) -Tail 10;throw 'Word context runtime assembly failed'}
$classes=Join-Path $root classes
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -proc:none -d $classes java/reference/WordContextReference.java
if($LASTEXITCODE -ne 0){throw 'Word context JVM oracle javac failed'}
& $inputs.java.executable --add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.base/sun.text=ALL-UNNAMED -cp $classes WordContextReference context (Join-Path $root jvm-context.bin) > (Join-Path $root context-reference.txt)
if($LASTEXITCODE -ne 0){throw 'JVM context property oracle failed'}
Add-Type -Path tests/host/WordContextProbe.cs
$nativeHash=[BoomWordContextProbe]::ContextHash((Join-Path $root boom-runtime.dll))
if($nativeHash -ne $p.context.codewords_sha256 -or $nativeHash -ne (Get-Content (Join-Path $root context-reference.txt)|Select-Object -Last 1) -or (Get-FileHash (Join-Path $root jvm-context.bin)).Hash.ToLowerInvariant() -ne $nativeHash){throw 'Exhaustive Unicode combining/cased context mismatch'}
$cases=[Collections.Generic.List[string]]::new()
foreach($s in @('-','0','ffff','41,ffff,3a3','41,3a3','41,27,3a3','41,301,3a3','41,2e,3a3','d800,41,3a3','41,dc00,3a3','d83d,de00,41,3a3','0e01,0e32,41,3a3','4e2d,41,3a3','41,110b,3a3','27,301,130,3c3,49,ae5b,d800,dc00,3a3,307','41,d800,dc00,3a3')){$cases.Add($s)}
for($i=0;$i -lt 256;$i++){$cases.Add("41,$($i.ToString('x')),3a3")}
$random=[Random]::new(62062)
for($i=0;$i -lt 1024;$i++){
 $length=$random.Next(0,65)
 if($length -eq 0){$cases.Add('-')}else{$cases.Add((@(for($j=0;$j -lt $length;$j++){if($i%2 -eq 0){$random.Next(128).ToString('x')}else{$random.Next(65536).ToString('x')}})) -join ',')}
}
$lines=$cases.ToArray();$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'WordContextReference','boundary')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Word JVM oracle failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$jvm.StandardInput.Write(($lines -join "`n")+"`n");$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Word reference timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})}finally{$jvm.Dispose()}
$actual=[BoomWordContextProbe]::Boundaries((Join-Path $root boom-runtime.dll),$lines,$true)
if($actual.Count -ne $expected.Count){throw 'Word boundary record count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Word boundary mismatch at $i input=$($lines[$i]) expected=$($expected[$i]) actual=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Word context compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';root_word_boundary_JVM_cases=$lines.Count;boundary_query_orders=3;forward_and_backward_DFA_checked=$true;unicode_context_code_points=0x110000;context_words_sha256=$nativeHash;locked_JDK_word_resource_sha256=$p.resource_sha256;source_state_count=$p.ends.Count;source_category_count=$p.categories;preserves_supplementary_duplicate_starts=$true;preserves_CharacterIterator_DONE_behavior=$true;no_guest_allocations=$true;data_is_VM_fixture=$true;original_Java_BreakIterator_executed=$false;String_lowercase_integration_tested=$false;dictionary_word_boundaries=$false;dynamic_locale_providers=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-word-context-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
