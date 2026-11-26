param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='',[string]$JdkModules='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
if(-not $JdkModules){$JdkModules=Join-Path ((Get-Content .boom/latest-jdk-modules.txt -Raw).Trim()) 'jdk-modules.json'}
$snapshot=Get-Content -LiteralPath $JdkModules -Raw|ConvertFrom-Json
$base=Get-Content -LiteralPath $JdkBase -Raw|ConvertFrom-Json
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
$root=Join-Path $projectRoot ('.boom\layer-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$names=@($snapshot.modules.PSObject.Properties.Name|Sort-Object)
$source=[Collections.Generic.List[string]]::new();$source.Add('package dev.boom.layers; final class Names { static String at(int n) { return switch(n) {')
for($i=0;$i -lt $names.Count;$i++){$source.Add("case $i -> `"$($names[$i])`";")}
$extras=@('"unknown.module"','"java.base\0"','"JAVA.BASE"','""','"java.base\ud800"','"jdk.jfr\udfff"')
for($i=0;$i -lt $extras.Count;$i++){$source.Add("case $($names.Count+$i) -> $($extras[$i]);")}
$source.Add('case -1 -> null; default -> "unknown"; }; } }')
$nameSource=Join-Path $root 'Names.java';[IO.File]::WriteAllText($nameSource,($source -join "`n"),[Text.UTF8Encoding]::new($false))
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes $nameSource (Join-Path $projectRoot 'java/subset/dev/boom/layers/LayerEntry.java') (Join-Path $projectRoot 'java/subset/dev/boom/subset/ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Layer reference javac failed'}
& scripts/Build-FpProbe.ps1 -Output $root
& scripts/Build-AssemblyRuntime.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/LayerProbe.cs
[BoomLayerProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
$argsList=@('compile-program','--entry-class','dev/boom/layers/LayerEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--jdk-modules',$JdkModules,'--assemble')
foreach($file in Get-ChildItem (Join-Path $classes 'dev/boom/layers') -Filter '*.class'){$argsList+=@('--class-file',$file.FullName)}
$methods=@('bootIdentity','ofClass','present','name','identity','dynamic','roundTrip','direct','types','noInit','nullModule','nullLayer','cached')
$programs=@{}
foreach($method in $methods){
    $text=& $Boom @argsList --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Layer compilation failed: $method"}
    $p=$text|ConvertFrom-Json;$programs[$method]=$p
    if($p.schema -ne 16 -or $p.module_plan.abi -ne 2 -or $p.module_plan.boot.snapshot_fingerprint -ne $snapshot.fingerprint -or $p.module_plan.identities.Count -ne (@($snapshot.graph.resolved.PSObject.Properties).Count+1) -or 'OFFSET boom_layer_layout' -notin $p.runtime_type_bindings.tag){throw 'Layer metadata/layout contract mismatch'}
    if($method -eq 'noInit' -and @($p.classes|Where-Object name -eq 'dev/boom/layers/Dormant').Count -ne 0){throw 'Layer query initialized its target'}
    if(@($p.symbols|Where-Object class_name -in @('java/lang/Class','java/lang/Module','java/lang/ModuleLayer')).Count -ne 0){throw 'Opaque VM Java representation was executed'}
    if($method -in @('present','name','identity','dynamic','roundTrip','nullLayer','cached')){
        $jdk=@($p.sources|Where-Object class_name -eq 'java/util/Optional')[0]
        if($jdk.digest.sha256 -ne $base.classes.'java.util.Optional'.sha256 -or @($p.symbols|Where-Object { $_.class_name -eq 'java/util/Optional' -and $_.method -eq 'ofNullable'}).Count -ne 1){throw 'Lookup did not compile original JDK Optional factory'}
    }
    if((Get-FileHash $p.compilation.dll).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256){throw 'Layer DLL changed'}
    Write-Output "Compiled layer entry: $method"
}
$selectors=@(0..($names.Count+$extras.Count-1)|ForEach-Object{$_.ToString('x')})+@('ffffffff','80000000','7fffffff')
$cases=[Collections.Generic.List[object]]::new()
foreach($selector in $selectors){
    foreach($empty in @('0','1')){foreach($method in @('present','name','identity')){$cases.Add([pscustomobject]@{method=$method;values=@($selector,$empty)})}}
    foreach($tail in @('0','1')){$cases.Add([pscustomobject]@{method='dynamic';values=@($selector,$tail)})}
    $cases.Add([pscustomobject]@{method='roundTrip';values=@($selector)})
}
foreach($value in @('0','1','2','3','7','ffffffff','80000000','7fffffff')){foreach($method in @('bootIdentity','ofClass','direct','types','noInit','nullModule','nullLayer','cached')){$cases.Add([pscustomobject]@{method=$method;values=@($value)})}}
function Reference([string[]]$records,[string[]]$options){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in ($options+@('-cp',$classes,'dev.boom.subset.ClassNumericOracle'))){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
    try{
        if(-not $oracle.Start()){throw 'Layer JVM reference failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
        if(-not $oracle.StandardInput.WriteAsync(($records -join "`n")+"`n").Wait(15000)){throw 'Layer oracle input stalled'};$oracle.StandardInput.Close()
        if(-not $oracle.WaitForExit(30000)){throw 'Layer oracle timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
}
$lines=@($cases|ForEach-Object{(@('dev.boom.layers.LayerEntry',$_.method,$programs[$_.method].compilation.descriptor)+@($_.values)) -join ' '})
$expected=@(Reference $lines @());if($expected.Count -ne $cases.Count){throw 'Layer oracle record count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}});[string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$init=@($programs['cached'].classes|Where-Object name -eq 'dev/boom/layers/Init')[0];$counter=@($init.fields|Where-Object name -eq 'count')[0]
[BoomLayerProbe]::Cold($programs['cached'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$init.id,$counter.index)
[int[]]$membership=@(for($n=0;$n -lt $names.Count;$n++){$at=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq 'roundTrip' -and $cases[$i].values[0] -eq $n.ToString('x')){$i}})[0];if($expected[$at] -eq 'v 0000000000000001'){1}else{0}})
[BoomLayerProbe]::Parallel($programs['direct'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$membership,$true)
[BoomLayerProbe]::Parallel($programs['roundTrip'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$membership,$false)
$text=& $Boom @argsList --method combined --enable-assertions --enable-system-assertions --output (Join-Path $root 'combined');if($LASTEXITCODE -ne 0){throw 'Layer/clock/assertion combination failed'};$combined=$text|ConvertFrom-Json
if($combined.schema -ne 16 -or $combined.bootstrap_mirror_abi -ne 2 -or -not $combined.assertion_policy.application_enabled -or -not $combined.assertion_policy.system_enabled -or $combined.vm_bindings.Count -ne 1){throw 'Combined layer contracts mismatch'}
$combinedExpected=@(Reference @($selectors|ForEach-Object{"dev.boom.layers.LayerEntry combined (I)I $_"}) @('-ea','-esa'))
$combinedActual=[BoomNumericProbe]::Run($combined.compilation.dll,(Join-Path $root 'fpstate.dll'),[string[]]$selectors,'I',$true)
for($i=0;$i -lt $selectors.Count;$i++){if($combinedActual[$i] -ne $combinedExpected[$i]){$failures.Add([pscustomobject]@{case="combined $($selectors[$i])";expected=$combinedExpected[$i];actual=$combinedActual[$i]})}}
$destination=Join-Path $root 'reject-unsupported'; & $Boom @argsList --method unsupported --output $destination 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $destination)){throw 'Unsupported layer collection operation accepted'}
$withoutGraph=@();for($i=0;$i -lt $argsList.Count;$i++){if($argsList[$i] -eq '--jdk-modules'){$i++}else{$withoutGraph+=$argsList[$i]}}
$destination=Join-Path $root 'reject-missing-graph'; & $Boom @withoutGraph --method roundTrip --output $destination 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $destination)){throw 'Unverified layer graph accepted'}
$report=[ordered]@{backend='boom-layers-program-v16-masm-x64';runtime_language='assembly';module_pool_abi=2;layer_pool_abi=1;snapshot_fingerprint=$snapshot.fingerprint;available_names=$names.Count;resolved_names=@($membership|Where-Object {$_ -eq 1}).Count;compiled_entries=($methods.Count+1);differential_cases=($cases.Count+$selectors.Count);native_executions=(($cases.Count+$selectors.Count)*2);original_jdk_Optional_factory=$true;boot_empty_and_module_layer_identity=$true;lookup_before_class_mirrors=$true;dynamic_utf16_names=$true;null_and_empty_layer_checks=$true;multicore_records=40975;cold_initializer_records=8195;direct_cold_and_post_gc_records=16390;lookup_cold_and_post_gc_records=16390;workers=8;quiescent_gc_roots=$true;temporary_Optional_reclamation=$true;assertion_and_clock_coexist=$true;native_abi_and_bad_metadata_checked=$true;dynamic_layers=$false;exports_readability_enforced=$false;other_jdk_class_providers=$false;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-layer-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1};exit 0
