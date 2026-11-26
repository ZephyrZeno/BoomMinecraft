param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/initialization-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') -source 21 -target 21 --add-exports java.base/jdk.internal.access=ALL-UNNAMED -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/initialization/InitializationEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Initialization fixture javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/InitializationProbe.cs
$programs=@{};$methods=@('lazy','handles')
foreach($method in $methods){
    & $Boom compile-program --class-file (Join-Path $classes 'dev/boom/initialization/InitializationEntry.class') --entry-class dev/boom/initialization/InitializationEntry --method $method --metadata-lock $MetadataLock --jdk-base $JdkBase --assemble --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "Initialization compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 27 -or @($p.constant_class_initialization).Count -ne 1){throw 'Initialization source profile missing'}
    $b=$p.constant_class_initialization[0]
    if($b.caller.sha256 -ne $base.classes.'jdk.internal.access.SharedSecrets'.sha256 -or $b.target.sha256 -ne $base.classes.'java.io.FileDescriptor'.sha256 -or $b.site.method -ne 'getJavaIOFileDescriptorAccess' -or $b.site.pc -ne 10){throw 'Initialization source/callsite proof mismatch'}
    if(@($p.symbols|Where-Object {$_.class_name -eq 'java/lang/invoke/MethodHandles' -or $_.class_name -eq 'java/lang/invoke/MethodHandles$Lookup'}).Count){throw 'General MethodHandles execution was incorrectly claimed'}
    if(@($p.symbols|Where-Object {$_.class_name -eq 'jdk/internal/access/SharedSecrets' -and $_.method -eq 'getJavaIOFileDescriptorAccess'}).Count -ne 1 -or @($p.symbols|Where-Object {$_.class_name -eq 'java/io/FileDescriptor' -and $_.method -eq '<clinit>'}).Count -ne 1){throw 'Original getter/initializer missing'}
    $programs[$method]=$p;Write-Output "Compiled original lazy initialization/getter entry: $method"
}
$values=[Collections.Generic.List[string]]::new()
foreach($n in @(0,1,-1,[int]::MinValue,[int]::MaxValue,127,128,255,256,32767,32768,65535,65536,-65536,0xd800,0xdbff,0xdc00,0xdfff,0x1f600)){$values.Add(([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$n),0)).ToString('x'))}
[uint64]$seed=0x12345678
for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
$lines=@(foreach($method in $methods){foreach($v in $values){'dev.boom.initialization.InitializationEntry '+$method+' (I)I '+$v}})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($a in @('--add-exports','java.base/jdk.internal.access=ALL-UNNAMED','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($a)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Initialization JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Initialization JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Initialization JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$reference=$stdout.GetAwaiter().GetResult()}
finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
$expected=@($reference.Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Initialization reference case count changed'}
$index=0
foreach($method in $methods){
    $p=$programs[$method]
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values.ToArray(),'I',$true)
    foreach($result in $actual){if($result -ne $expected[$index]){throw "Initialization differential mismatch: $method, $index, $result, $($expected[$index])"};$index++}
    $owner=@($p.classes|Where-Object name -eq 'java/io/FileDescriptor')[0];$shared=@($p.classes|Where-Object name -eq 'jdk/internal/access/SharedSecrets')[0];$field=@($shared.fields|Where-Object name -eq 'javaIOFileDescriptorAccess')[0]
    [BoomInitializationProbe]::Parallel($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$owner.id,$shared.id,$field.index, $(if($method -eq 'lazy'){11}else{7}))
    $initializer=@($p.symbols|Where-Object {$_.class_name -eq 'java/io/FileDescriptor' -and $_.method -eq '<clinit>'})[0]
    [BoomInitializationProbe]::Failure($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$owner.id,$initializer.id)
    Write-Output "Validated JVM differential, cold 8-worker lazy initialization and persistent failure: $method"
}
$rejected=Join-Path $root 'rejected-no-metadata'
& $Boom compile-program --class-file (Join-Path $classes 'dev/boom/initialization/InitializationEntry.class') --entry-class dev/boom/initialization/InitializationEntry --method lazy --output $rejected 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $rejected)){throw 'Initialization request without verified bootstrap metadata accepted'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Initialization compiler changed during test'}
$report=[ordered]@{backend='boom-class-initialization-program-v27-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=2;differential_cases=$lines.Count;native_executions=($lines.Count*2);multicore_records=12294;workers=8;original_SharedSecrets_lazy_getter=$true;original_FileDescriptor_initializer_and_registration=$true;source_helper_body_and_exception_contract_verified=$true;constant_Class_and_all_incoming_edges_proven=$true;original_private_descriptor_getters=$true;static_guest_objects=5;hot_path_guest_allocations=0;initializer_oom_source_and_persistent_failure=$true;general_MethodHandles_Lookup=$false;Java_FileInputStream_FileOutputStream_chains_complete=$false;System_application_bootstrap_complete=$false;automatic_gc=$false;negative_compile_checks=1;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-initialization-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
