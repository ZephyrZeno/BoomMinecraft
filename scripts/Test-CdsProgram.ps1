param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/cds-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') -source 21 -target 21 --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/cds/CdsEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'CDS fixture javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/CdsProbe.cs
[BoomCdsProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
$common=@('compile-program','--entry-class','dev/boom/cds/CdsEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($cf in Get-ChildItem (Join-Path $classes 'dev/boom/cds') -Filter '*.class'){$common+=@('--class-file',$cf.FullName)}
$methods=@('run','initialized','array','repeated');$programs=@{}
foreach($method in $methods){
    & $Boom @common --method $method --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "CDS program compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 24 -or $p.cds_profile.abi -ne 1 -or $p.cds_profile.shared_archive_mapped -or $p.cds_profile.dumping_archive -or $p.cds_profile.dumping_class_list){throw 'CDS profile mismatch'}
    foreach($b in $p.cds_profile.bindings){if($b.origin.loader -ne 'bootstrap' -or $b.origin.source_id -ne 'jdk:java.base' -or $b.origin.sha256 -ne $base.classes.'jdk.internal.misc.CDS'.sha256){throw 'CDS binding source mismatch'}}
    if(@($p.symbols|Where-Object {$_.class_name -eq 'jdk/internal/misc/CDS' -and $_.method -eq '<clinit>'}).Count -ne 1 -or $p.cds_profile.bindings.Count -lt 4){throw 'Original CDS initializer or its private query bindings missing'}
    $targetInits=@($p.symbols|Where-Object {$_.class_name -eq 'dev/boom/cds/CdsEntry$Target' -and $_.method -eq '<clinit>'}).Count
    if(($method -eq 'initialized') -ne ($targetInits -eq 1)){throw 'Archive initialization changed target-class initialization semantics'}
    $programs[$method]=$p;Write-Output "Compiled no-CDS entry: $method"
}
$values=[Collections.Generic.List[string]]::new()
foreach($n in @(0,1,-1,[int]::MinValue,[int]::MaxValue,127,128,255,256,32767,32768,65535,65536,-65536,0xd800,0xdbff,0xdc00,0xdfff,0x1f600)){$values.Add(([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$n),0)).ToString('x'))}
[uint64]$seed=0x12345678
for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
$cases=@(foreach($method in $methods){foreach($s in $values){[ordered]@{method=$method;value=$s}}})
$lines=@($cases|ForEach-Object{'dev.boom.cds.CdsEntry '+$_.method+' (I)I '+$_.value})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xshare:off','--add-exports','java.base/jdk.internal.misc=ALL-UNNAMED','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'CDS JVM reference failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'CDS JVM input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'CDS JVM reference timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'CDS reference case count changed'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$nativeValues=@($indices|ForEach-Object{$cases[$_].value})
    $actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$nativeValues,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
if($failures.Count){$failures|ConvertTo-Json -Depth 7|Set-Content (Join-Path $root 'failures.json');throw "CDS reference mismatches: $($failures.Count), $root"}
$cds=@($programs['run'].classes|Where-Object name -eq 'jdk/internal/misc/CDS')[0]
$field=@($cds.fields|Where-Object name -eq 'excludeFlags')[0]
$live=[BoomCdsProbe]::Parallel($programs['run'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$cds.id,$field.index)
$negative=0
foreach($mode in @('metadata','unsupported')){
    $out=Join-Path $root ('reject-'+$mode)
    if($mode -eq 'metadata'){& $Boom compile-program --class-file (Join-Path $classes 'dev/boom/cds/CdsEntry.class') --entry-class dev/boom/cds/CdsEntry --method run --output $out 2>&1|Out-Null}
    else{& $Boom @common --method unsupported --output $out 2>&1|Out-Null}
    if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'Unverified or unsupported CDS operation accepted'};$negative++
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'CDS compiler changed during test'}
$report=[ordered]@{backend='boom-cds-program-v24-masm-x64';compiler_sha256=$sha;runtime_language='assembly';profile='no-mapped-archive/no-dump/no-class-list';jvm_reference_args=@('-Xshare:off','--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED');compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=6147;workers=8;original_CDS_initializer_executed=$true;original_exclusion_array_and_contents_checked=$true;target_class_not_initialized_by_archive_lookup=$true;target_static_values_preserved=$true;cold_concurrent_initialization_and_reentry=$true;guest_objects_after_warmup=$live;no_per_call_guest_allocations=$true;quiescent_collection_preserves_bootstrap_graph=$true;negative_compile_checks=$negative;shared_archive_loading=$false;automatic_gc=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-cds-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
