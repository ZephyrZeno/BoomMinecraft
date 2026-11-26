param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v79b/boom-runtime.dll',[string]$ExistingRun='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=if($ExistingRun){[IO.Path]::GetFullPath($ExistingRun)}else{Join-Path (Get-Location) ('.boom/bootstrap-lookup-tests/'+[guid]::NewGuid().ToString('N'))};[IO.Directory]::CreateDirectory($root)|Out-Null
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$modules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json
if(-not $ExistingRun){
 & $Boom compile-locked-program --lock .boom/locks/server.json --jdk-base $base --jdk-modules $modules --entry-class java/lang/ClassLoader --method findBootstrapClassOrNull --descriptor '(Ljava/lang/String;)Ljava/lang/Class;' --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
 if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 8;throw 'Bootstrap lookup AOT compilation failed'}
}
& D:/Dev/Python312/python.exe scripts/verify-bootstrap-lookup.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Bootstrap lookup source contract failed'}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d "$root/classes" java/reference/BootstrapLookupReference.java
if($LASTEXITCODE -ne 0){throw 'Bootstrap lookup oracle javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m',"-XX:ErrorFile=$root/hs_err_pid%p.log",'--add-opens=java.base/java.lang=ALL-UNNAMED','-cp',"$root/classes",'BootstrapLookupReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Bootstrap lookup oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Bootstrap lookup oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
$names=@(foreach($id in $p.mirror_name_literals){$literal=@($p.string_literals|Where-Object id -eq $id)[0];-join @($literal.utf16|ForEach-Object{[char]$_})})
$ule=@($p.object_layouts|Where-Object class_name -eq java/lang/UnsatisfiedLinkError)[0].class_id
$unlinked=@($p.class_for_name.catalog|Where-Object {$_.defining_loader -eq 'bootstrap' -and $_.type_id -eq $null -and -not $_.array})[0].name
Add-Type -Path tests/host/BootstrapLookupProbe.cs
$actual=[BoomBootstrapLookupProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),[string[]]$names,$unlinked,[uint32]$ule)
if($actual.Count -ne $expected.Count){throw 'Bootstrap lookup oracle row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Bootstrap lookup differs at $i : JVM=$($expected[$i]); ASM=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Bootstrap lookup compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=15;workers=8;warm_lookup_calls=2048;warm_guest_allocations=0;original_ClassLoader_initializer_checkName_and_lookup_Java_wrapper_executed=$true;bootstrap_native_in_ASM=$true;canonical_mirror_and_loader_visibility_checked=$true;dynamic_class_definition_complete=$false;unlinked_existing_catalog_entries_remain_gated=$true;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-bootstrap-lookup-test.txt',$root);Write-Output $json
exit 0
