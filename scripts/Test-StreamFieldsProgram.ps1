param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/stream-fields-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/initialization/StreamInitialization.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Stream initialization javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/StreamFieldsProbe.cs
$programs=@{};$kinds=@('Input','Output')
foreach($kind in $kinds){
    $arguments=@('compile-program','--entry-class',('dev/boom/initialization/StreamInitialization$'+$kind),'--method','run','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble','--output',(Join-Path $root $kind))
    foreach($file in Get-ChildItem (Join-Path $classes 'dev/boom/initialization') -Filter 'StreamInitialization*.class'){$arguments+=@('--class-file',$file.FullName)}
    & $Boom @arguments > (Join-Path $root ($kind+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "Stream initialization compilation failed: $kind"}
    $p=Get-Content (Join-Path $root ($kind+'/program.json')) -Raw|ConvertFrom-Json
    $name='java/io/File'+$kind+'Stream';$b=$p.file_streams[0]
    if($p.schema -ne 28 -or $p.initializer_source_abi -ne 2 -or @($p.file_streams).Count -ne 1 -or $b.origin.binary_name -ne $name.Replace('/','.') -or $b.origin.sha256 -ne $base.classes.($b.origin.binary_name).sha256 -or $b.descriptor_origin.sha256 -ne $base.classes.'java.io.FileDescriptor'.sha256 -or @($b.bindings).Count -ne 1){throw 'Stream native source proof mismatch'}
    if(@($p.symbols|Where-Object {$_.class_name -eq $name -and $_.method -eq '<clinit>'}).Count -ne 1 -or @($p.symbols|Where-Object {$_.method -eq '<init>' -and $_.class_name -in @('java/io/FileInputStream','java/io/FileOutputStream')}).Count){throw 'Original stream initialization scope mismatch'}
    if($kind -eq 'Input' -and ($null -ne $p.constant_class_initialization -or $null -ne $p.file_descriptors)){throw 'Input initIDs incorrectly activated FileDescriptor'}
    if($kind -eq 'Output' -and (@($p.constant_class_initialization).Count -ne 1 -or $p.file_descriptors.bindings.Count -ne 3)){throw 'Original output lazy registration missing'}
    $programs[$kind]=$p;Write-Output "Compiled original stream class initializer: $kind"
}
$values=[Collections.Generic.List[string]]::new()
foreach($n in @(0,1,-1,[int]::MinValue,[int]::MaxValue,127,128,255,256,32767,32768,65535,65536,-65536,0xd800,0xdbff,0xdc00,0xdfff,0x1f600)){$values.Add(([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$n),0)).ToString('x'))}
[uint64]$seed=0x12345678
for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
$lines=@(foreach($kind in $kinds){foreach($v in $values){'dev.boom.initialization.StreamInitialization$'+$kind+' run (I)I '+$v}})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($a in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($a)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Stream JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Stream JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Stream JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$reference=$stdout.GetAwaiter().GetResult()}
finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
$expected=@($reference.Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Stream reference case count changed'}
$index=0
foreach($kind in $kinds){
    $p=$programs[$kind];$actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values.ToArray(),'I',$true)
    foreach($result in $actual){if($result -ne $expected[$index]){throw "Stream differential mismatch: $kind, $index, $result, $($expected[$index])"};$index++}
    $fdOwner=0;$outputField=0;$increment=1;$retained=0;$accessField=0;$sharedOwner=0;$sharedField=0
    if($kind -eq 'Output'){$fd=@($p.classes|Where-Object name -eq 'java/io/FileDescriptor')[0];$fdOwner=$fd.id;$outputField=@($fd.fields|Where-Object name -eq 'out')[0].index;$increment=2;$retained=5;$stream=@($p.classes|Where-Object name -eq 'java/io/FileOutputStream')[0];$accessField=@($stream.fields|Where-Object name -eq 'FD_ACCESS')[0].index;$shared=@($p.classes|Where-Object name -eq 'jdk/internal/access/SharedSecrets')[0];$sharedOwner=$shared.id;$sharedField=@($shared.fields|Where-Object name -eq 'javaIOFileDescriptorAccess')[0].index}
    [BoomStreamFieldsProbe]::Parallel($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$p.file_streams[0].class_id,$increment,$retained,$fdOwner,$outputField,$accessField,$sharedOwner,$sharedField)
    $failureName=if($kind -eq 'Output'){'java/io/FileDescriptor'}else{'java/io/FileInputStream'}
    $failureOwner=@($p.classes|Where-Object name -eq $failureName)[0]
    $failureInitializer=@($p.symbols|Where-Object {$_.class_name -eq $failureName -and $_.method -eq '<clinit>'})[0]
    [BoomStreamFieldsProbe]::Failure($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$p.file_streams[0].class_id,$failureOwner.id,$failureInitializer.id,($kind -eq 'Output'))
    Write-Output "Validated stream original initializer, cold workers, field table and raw field access: $kind"
}
$out=Join-Path $root 'rejected-no-metadata'
& $Boom compile-program --class-file (Join-Path $classes 'dev/boom/initialization/StreamInitialization$Input.class') --entry-class 'dev/boom/initialization/StreamInitialization$Input' --method run --output $out 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'Stream initialization without original bootstrap metadata accepted'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Stream compiler changed during run'}
$report=[ordered]@{backend='boom-stream-fields-program-v28-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=2;differential_cases=$lines.Count;native_executions=($lines.Count*2);multicore_records=12294;workers=8;original_FileInputStream_and_FileOutputStream_initializers=$true;source_private_native_and_final_field_proven=$true;actual_reference_field_table_validated_and_atomically_published=$true;output_FD_ACCESS_uses_original_lazy_getter=$true;input_initIDs_does_not_initialize_FileDescriptor=$true;raw_runtime_field_lookup_verified=$true;null_wrong_layout_unpublished_conflicting_and_corrupt_tables_checked=$true;initializer_native_error_and_nested_OOM_source_persistent_failure=$true;field_access_guest_temporaries=0;input_static_guest_objects=0;output_static_guest_objects=5;Java_stream_constructors_executed=$false;Java_stream_read_write_wrappers_complete=$false;automatic_gc=$false;System_application_bootstrap_complete=$false;negative_compile_checks=1;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-stream-fields-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
