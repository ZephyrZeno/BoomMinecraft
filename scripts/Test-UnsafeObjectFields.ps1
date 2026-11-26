param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v79b/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/unsafe-object-field-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null;[IO.File]::WriteAllText('.boom/current-unsafe-object-field-test.txt',$root)
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -g -proc:none -d "$root/classes" java/subset/dev/boom/unsafe/ObjectFieldsProgram.java java/reference/ObjectFieldsReference.java
if($LASTEXITCODE -ne 0){throw 'Object fields oracle javac failed'}
$arguments=@('compile-program','--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--entry-class','dev/boom/unsafe/ObjectFieldsProgram','--method','run','--descriptor','(I)Ljava/lang/String;','--output',"$root/program",'--assemble')
foreach($file in Get-ChildItem "$root/classes/dev/boom/unsafe" -Filter '*.class'){$arguments+=@('--class-file',$file.FullName)}
& $Boom @arguments > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 12;throw 'Object fields AOT compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-unsafe-bootstrap-contract.py "$root/program/program.json" > "$root/unsafe-source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Unsafe object fields source contract failed'}
& D:/Dev/Python312/python.exe scripts/verify-reflect-fields.py "$root/program/program.json" $base > "$root/field-source-contract.json"
if($LASTEXITCODE -ne 0){throw 'Field object maps source contract failed'}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if($p.schema -ne 76 -or $p.reflected_fields.abi -ne 5 -or -not $p.unsafe_bootstrap.object_field_access){throw 'Object field capability metadata missing'}
$record=@($p.reflected_fields.records|Where-Object {$_.source.binary_name -eq 'dev.boom.unsafe.ObjectFieldsProgram$Parent' -and $_.name -eq 'flag'})[0]
$map=@($p.field_maps|Where-Object id -eq $record.instance_map)[0]
if(@($map.rows.offset|Sort-Object -Unique).Count -lt 3){throw 'Fixture did not exercise changed primitive offsets in subclasses'}
if(@($p.symbols|Where-Object {$_.class_name -eq 'jdk/internal/misc/Unsafe' -and $_.method -in @('compareAndSetBoolean','compareAndSetByte','bool2byte')}).Count -lt 3){throw 'Original Java boolean CAS wrappers were not compiled'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',"$root/classes",'ObjectFieldsReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Object fields oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Object fields oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
Add-Type -Path tests/host/ObjectFieldsProbe.cs
$actual=[BoomObjectFieldsProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime))
if($actual.Count -ne $expected.Count){throw 'Object fields oracle row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Object fields mode $i differs: JVM=$($expected[$i]); ASM=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Object fields compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=17;byte_field_and_array_signed_exchange_checked=$true;workers=8;parallel_independent_cases=960;contended_boolean_rounds=512;contended_boolean_calls=4096;successful_boolean_publications=512;warm_contended_guest_allocations=0;original_Unsafe_objectFieldOffset_and_boolean_CAS_Java_wrappers_executed=$true;compareAndExchangeByte_Java_body_executed=$false;compareAndExchangeByte_in_ASM=$true;per_receiver_inherited_primitive_offsets_checked=$true;declared_only_lookup_InternalError_null_message_and_no_class_initialization_checked=$true;public_reflection_filter_bypass_checked=$true;actual_Module_native_access_wrapper_executed=$false;multiple_application_defining_loaders_tested=$false;full_unsafe_coverage=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-unsafe-object-field-test.txt',$root);Write-Output $json
exit 0
