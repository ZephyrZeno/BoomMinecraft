param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v73-display/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/field-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-field-test.txt',$root)
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d "$root/classes" java/subset/dev/boom/fields/FieldProgram.java java/reference/FieldReference.java
if($LASTEXITCODE -ne 0){throw 'Field fixture javac failed'}
$files=@('FieldProgram','FieldProgram$Parent','FieldProgram$Target','FieldProgram$Tiny')
foreach($member in @(@('run','(II)J'),@('raw','(I)Ljava/lang/reflect/Field;'))){
    $arguments=@('compile-program','--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--entry-class','dev/boom/fields/FieldProgram','--method',$member[0],'--descriptor',$member[1],'--output',"$root/$($member[0])",'--assemble')
    foreach($name in $files){$arguments+=@('--class-file',"$root/classes/dev/boom/fields/$name.class")}
    & $Boom @arguments > "$root/$($member[0])-compile.json" 2> "$root/$($member[0])-compile.err"
    if($LASTEXITCODE -ne 0){Get-Content "$root/$($member[0])-compile.err" -Tail 8;throw "Field $($member[0]) compilation failed"}
}
$cases=[Collections.Generic.List[string]]::new();$cases.Add('0 0');$cases.Add('11 0');$cases.Add('10 0');$cases.Add('11 0')
foreach($mode in 0..5){foreach($which in 0..21){$cases.Add("$mode $which")}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',"$root/classes",'FieldReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Field oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$jvm.StandardInput.Write(($cases -join "`n")+"`n");$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Field oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
Add-Type -Path tests/host/FieldProbe.cs
$run=Get-Content "$root/run/program.json" -Raw|ConvertFrom-Json;$raw=Get-Content "$root/raw/program.json" -Raw|ConvertFrom-Json
foreach($member in @('run','raw')){& D:/Dev/Python312/python.exe scripts/verify-reflect-fields.py "$root/$member/program.json" $base > "$root/$member-source-contract.json";if($LASTEXITCODE -ne 0){throw 'Independent Field source proof failed'}}
$actual=[BoomFieldProbe]::Run($run.compilation.dll,[IO.Path]::GetFullPath($Runtime),$cases.ToArray())
if($actual.Count -ne $expected.Count){throw 'Field oracle row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Field mismatch at $($cases[$i]): JVM=$($expected[$i]) ASM=$($actual[$i])"}}
[BoomFieldProbe]::CheckAbi($raw.compilation.dll,[IO.Path]::GetFullPath($Runtime))
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Field compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';compiled_entries=2;JVM_metadata_identity_and_error_cases=$cases.Count;lookup_does_not_initialize_target_checked=$true;JDK_bootstrap_field_filters_checked=$true;NoSuchFieldException_preserves_requested_name=$true;workers=8;parallel_lookup_equality_calls=1024;full_runtime_Field_and_static_address_ABI_checked=$true;live_and_temporary_Field_GC_checked=$true;original_Class_and_Field_API_bodies_executed=$false;value_access_complete=$false;dynamic_filter_registration_supported=$false;generic_reflection_complete=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText("$root/oracle.json",($expected|ConvertTo-Json),[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-field-test.txt',$root);Write-Output $json
exit 0
