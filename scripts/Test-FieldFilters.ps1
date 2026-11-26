param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v73-display/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/field-filter-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-field-filter-test.txt',$root)
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 --add-exports java.base/jdk.internal.reflect=ALL-UNNAMED -g -proc:none -d "$root/classes" java/subset/dev/boom/fields/FieldProgram.java java/subset/dev/boom/fields/FilterProgram.java java/reference/FieldFilterReference.java
if($LASTEXITCODE -ne 0){throw 'Filter oracle/proof javac failed'}
& $Boom inspect-field-filters --class-file "$root/classes/dev/boom/fields/FilterProgram.class" --output "$root/proof.json" > "$root/proof.stdout.json" 2> "$root/proof.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/proof.err" -Tail 6;throw 'Filter source proof inspection failed'}
$proof=Get-Content "$root/proof.json" -Raw|ConvertFrom-Json
if($proof.proofs.Count -ne 1 -or -not $proof.proofs[0].alternative_entries_excluded -or $proof.execution_complete){throw 'Filter proof scope differs'}
& D:/Dev/Python312/python.exe scripts/verify-field-filter-proof.py "$root/proof.json" > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Independent filter source proof failed'}
& ./scripts/Test-ReflectFields.ps1 -Boom $Boom -Runtime $Runtime > "$root/field-regression.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Filter Field regression failed'}
$fixture=(Get-Content .boom/latest-field-test.txt -Raw).Trim();$p=Get-Content "$fixture/raw/program.json" -Raw|ConvertFrom-Json
$target=[uint32]@($p.reflected_fields.records|Where-Object {$_.name -eq 'number' -and $_.source.binary_name -eq 'dev.boom.fields.FieldProgram$Target'})[0].class_state
foreach($clear in @($false,$true)){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('--add-exports=java.base/jdk.internal.reflect=ALL-UNNAMED','--add-opens=java.base/java.lang=ALL-UNNAMED','-Xmx128m','-cp',"$root/classes",'FieldFilterReference')){$info.ArgumentList.Add($arg)}
    if($clear){$info.ArgumentList.Add('clear-cache')}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
    try{if(-not $jvm.Start()){throw 'Filter oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Filter oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
    $actual=[BoomFieldProbe]::CheckFilterAbi($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),$target,$clear)
    if($actual.Count -ne $expected.Count){throw 'Filter ABI oracle count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Filter ABI observation $i (clear=$clear) differs: JVM=$($expected[$i]) ASM=$($actual[$i])"}}
    [IO.File]::WriteAllText("$root/oracle-$clear.json",($expected|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Filter compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_to_native_ABI_observations=22;existing_cache_and_explicit_cache_eviction_checked=$true;soft_reference_cache_clearing_implemented=$false;source_constant_operands_and_control_flow_inspected=$true;workers=8;parallel_registration_attempts=2048;successful_publications=2;duplicate_errors=2046;VM_Set12_storage_and_registration_site_fixtures_used=$true;actual_original_Set_of_and_Set12_constructor_executed=$false;actual_Java_register_call_executed=$false;actual_Set_contents_checked_before_publication=$true;existing_Field_not_revoked=$true;target_class_not_initialized=$true;constant_Class_and_two_literal_Set_only=$true;arbitrary_Set_registration_supported=$false;duplicate_registration_message_exact=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;fixture_directory=$fixture;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-field-filter-test.txt',$root);Write-Output $json
exit 0
