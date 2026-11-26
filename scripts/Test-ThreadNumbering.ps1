param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v73-display/boom-runtime.dll',[string]$ExistingProgram='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/thread-numbering-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$program=if($ExistingProgram){[IO.Path]::GetFullPath($ExistingProgram)}else{Join-Path $root program}
if(-not $ExistingProgram){& $Boom compile-locked-program --lock .boom/locks/server.json --jdk-base $base --entry-class 'java/lang/Thread$ThreadNumbering' --method next --descriptor '()I' --output $program --assemble > "$root/compile.json" 2> "$root/compile.err";if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 8;throw 'Thread numbering compilation failed'}}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -d "$root/classes" java/reference/ThreadNumberingReference.java
if($LASTEXITCODE -ne 0){throw 'Thread numbering oracle javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('--add-opens=java.base/java.lang=ALL-UNNAMED','-Xmx64m','-cp',"$root/classes",'ThreadNumberingReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Thread oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Thread oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};if($stdout.GetAwaiter().GetResult().Trim() -ne 'sequential_cases=32;overflow_cases=5'){throw 'Thread oracle sequence differs'}}finally{$jvm.Dispose()}
$p=Get-Content "$program/program.json" -Raw|ConvertFrom-Json
if(-not $p.reflected_fields -or -not $p.unsafe_bootstrap.static_field_access){throw 'Thread field/Unsafe linkage missing'}
& D:/Dev/Python312/python.exe scripts/verify-reflect-fields.py "$program/program.json" $base > "$root/field-source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Thread Field source proof failed'}
$owner=@($p.classes|Where-Object name -eq 'java/lang/Thread$ThreadNumbering')[0];$slot=[uint32]@($owner.fields|Where-Object name -eq next)[0].index
& D:/Dev/Python312/python.exe scripts/verify-unsafe-bootstrap-contract.py "$program/program.json" > "$root/unsafe-source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Unsafe source proof failed'}
Add-Type -Path tests/host/ThreadNumberingProbe.cs
[BoomThreadNumberingProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),[uint32]$owner.id,$slot)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Thread numbering compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();program=$program;runtime_language='assembly';original_ThreadNumbering_initializer_and_next_executed=$true;original_Unsafe_static_field_wrappers_getAndAddInt_and_weak_CAS_executed=$true;workers=8;contended_number_allocations=8192;warm_zero_Java_allocation_calls=256;JVM_sequence_cases=32;JVM_signed_overflow_cases=5;canonical_static_cell_and_quiescent_GC_checked=$true;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-thread-numbering-test.txt',$root);Write-Output $json
exit 0
