param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v71/boom-runtime.dll')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/inet-availability-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-inet-availability-test.txt',$root)
& ./scripts/Test-InetAddressCache.ps1 -Boom $Boom -Runtime $Runtime > "$root/cache-test.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'InetAddress cache test failed'}
$fixture=(Get-Content .boom/latest-inet-cache-test.txt -Raw).Trim()
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -d "$root/classes" java/reference/InetAvailabilityReference.java
if($LASTEXITCODE -ne 0){throw 'Availability reference javac failed'}
$preferences=[string[]]::new(10)
$tail=[string[]]@('','false','true','TRUE','TrUe',' true','true ','1','ｔｒｕｅ')
[Array]::Copy($tail,0,$preferences,1,$tail.Length)
$expected=[Collections.Generic.List[string]]::new()
foreach($preference in $preferences){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-Xmx64m','--add-opens=java.base/java.net=ALL-UNNAMED')){$info.ArgumentList.Add($arg)}
    if($null -ne $preference){$info.ArgumentList.Add('-Djava.net.preferIPv4Stack='+$preference)}
    foreach($arg in @('-cp',"$root/classes",'InetAvailabilityReference')){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{if(-not $process.Start()){throw 'Availability oracle did not start'};$stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync();if(-not $process.WaitForExit(15000)){$process.Kill($true);throw 'Availability oracle timeout'};if($process.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$value=$stdout.GetAwaiter().GetResult().Trim();if($value -notmatch '^[01] [01]$'){throw 'Invalid JVM availability pair'};$expected.Add($value)}finally{$process.Dispose()}
}
Add-Type -Path tests/host/InetAvailabilityProbe.cs
[BoomInetAvailabilityProbe]::Run("$fixture/cache.dll",[IO.Path]::GetFullPath($Runtime),$preferences,$expected.ToArray())
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Availability compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;full_runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_property_cases=$preferences.Count;native_query_calls=1024*$preferences.Count;workers=8;actual_Winsock_address_family_probes=$true;single_cold_publication_per_property=$true;changed_property_after_initialization_preserves_cache=$true;Java_heap_allocations_in_query=0;pending_metadata_foreign_heap_and_recovery_checked=$true;VM_metadata_and_String_fixtures_used=$true;original_InetAddress_Java_initializer_executed=$false;native_library_load_lifecycle_complete=$false;network_backend_complete=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;fixture_directory=$fixture;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText("$root/JVM-expected.json",($expected|ConvertTo-Json),[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-inet-availability-test.txt',$root);Write-Output $json
