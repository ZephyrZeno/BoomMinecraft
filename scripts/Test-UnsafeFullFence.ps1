param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v75/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/unsafe-fence-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-unsafe-fence-test.txt',$root)
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -g -proc:none -d "$root/classes" java/subset/dev/boom/unsafe/FenceProgram.java java/reference/FenceReference.java
if($LASTEXITCODE -ne 0){throw 'Fence oracle javac failed'}
& $Boom compile-program --class-file "$root/classes/dev/boom/unsafe/FenceProgram.class" --metadata-lock .boom/locks/server.json --jdk-base $base --entry-class dev/boom/unsafe/FenceProgram --method run --descriptor '(I)I' --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 10;throw 'Fence AOT compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-unsafe-bootstrap-contract.py "$root/program/program.json" > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Fence source contract verification failed'}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if(@($p.unsafe_bootstrap.bindings|Where-Object operation -eq FullFence).Count -ne 1){throw 'Original fullFence binding missing'}
$state=@($p.classes|Where-Object name -eq dev/boom/unsafe/FenceProgram)[0];foreach($field in $state.fields|Where-Object {$_.name -in @('x','y')}){if(($field.access -band 64) -ne 0){throw 'Litmus must use plain fields'}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',"$root/classes",'FenceReference','32768')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Fence oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(45000)){$jvm.Kill($true);throw 'Fence oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};if($stdout.GetAwaiter().GetResult().Trim() -ne 'rounds=32768;forbidden=0'){throw 'Fence JVM oracle differs'}}finally{$jvm.Dispose()}
Add-Type -Path tests/host/FenceProbe.cs
[BoomFenceProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),32768)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Fence compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';original_Java_stores_fullFence_loads_and_resets_executed=$true;original_Unsafe_bootstrap_executed=$true;workers=2;rounds=32768;native_fenced_operations=65536;JVM_reference_rounds=32768;forbidden_zero_zero_outcomes=0;warm_guest_allocations=0;full_unsafe_coverage=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-unsafe-fence-test.txt',$root);Write-Output $json
exit 0
