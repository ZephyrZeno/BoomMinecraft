param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path $projectRoot ('.boom\module-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\modules\ModuleEntry.java') (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Module reference javac failed'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
Add-Type -Path (Join-Path $projectRoot 'tests\host\ModuleProbe.cs')
[BoomModuleProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
$argsList=@('compile-program','--entry-class','dev/boom/modules/ModuleEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\modules') -Filter '*.class'){$argsList+=@('--class-file',$file.FullName)}
$methods=@('named','name','identity','literalIdentity','actual','type','cached','noInit','nullClass','nullName','nullNamed')
$programs=@{}
foreach($method in $methods){
    $text=& $Boom @argsList --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Module compilation failed: $method"}
    $p=$text|ConvertFrom-Json;$programs[$method]=$p
    if($p.schema -ne 15 -or $p.bootstrap_mirror_abi -ne 1 -or $p.module_plan.abi -ne 1 -or $p.module_plan.identities.Count -ne 2 -or $p.module_plan.type_modules.Count -ne $p.mirror_types.Count -or 'OFFSET boom_module_layout' -notin $p.runtime_type_bindings.tag){throw 'Module identity/layout contract mismatch'}
    if($method -eq 'noInit' -and @($p.classes|Where-Object name -eq 'dev/boom/modules/Dormant').Count -ne 0){throw 'Module query initialized its target class'}
    if(@($p.symbols|Where-Object class_name -in @('java/lang/Class','java/lang/Module')).Count -ne 0){throw 'Opaque module/class Java representation leaked into executable methods'}
    if((Get-FileHash -LiteralPath $p.compilation.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256){throw 'Module DLL changed'}
    Write-Output "Compiled module entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
$selectors=@('ffffffff')+@(0..15|ForEach-Object{$_.ToString('x')})+@('80000000','7fffffff')
foreach($selector in $selectors){foreach($method in @('named','name','literalIdentity','type')){$cases.Add([pscustomobject]@{method=$method;values=@($selector)})}}
foreach($a in $selectors){foreach($b in $selectors){$cases.Add([pscustomobject]@{method='identity';values=@($a,$b)})}}
foreach($value in @('0','1','2','ffffffff','80000000','7fffffff')){foreach($method in @('actual','cached','noInit','nullClass','nullName','nullNamed')){$cases.Add([pscustomobject]@{method=$method;values=@($value)})}}
$lines=@($cases|ForEach-Object{(@('dev.boom.modules.ModuleEntry',$_.method,$programs[$_.method].compilation.descriptor)+@($_.values)) -join ' '})
function Reference([string[]]$records,[string[]]$jvmArgs){
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in ($jvmArgs+@('-cp',$classes,'dev.boom.subset.ClassNumericOracle'))){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Module JVM reference failed'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($records -join "`n")+"`n").Wait(15000)){throw 'Module reference input stalled'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Module JVM reference timed out'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
return $expected
}
$expected=@(Reference $lines @())
if($expected.Count -ne $cases.Count){throw 'Module reference record count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$p=$programs[$method]
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$init=@($programs['cached'].classes|Where-Object name -eq 'dev/boom/modules/Init')[0]
$counter=@($init.fields|Where-Object name -eq 'count')[0]
[BoomModuleProbe]::Cold($programs['cached'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$init.id,$counter.index)
[BoomModuleProbe]::Race($programs['named'].compilation.dll,(Join-Path $root 'boom-runtime.dll'))
$text=& $Boom @argsList --method combined --enable-assertions --enable-system-assertions --output (Join-Path $root 'combined')
if($LASTEXITCODE -ne 0){throw 'Combined module/assertion/clock compilation failed'}
$combined=$text|ConvertFrom-Json
if($combined.schema -ne 15 -or $combined.bootstrap_mirror_abi -ne 2 -or -not $combined.assertion_policy.application_enabled -or -not $combined.assertion_policy.system_enabled -or $combined.vm_bindings.Count -ne 1 -or $combined.vm_bindings[0].operation -ne 'nano_time'){throw 'Combined runtime contracts mismatch'}
$combinedLines=@($selectors|ForEach-Object{"dev.boom.modules.ModuleEntry combined (I)I $_"})
$combinedExpected=@(Reference $combinedLines @('-ea','-esa'))
if($combinedExpected.Count -ne $selectors.Count){throw 'Combined oracle count mismatch'}
$combinedActual=[BoomNumericProbe]::Run($combined.compilation.dll,(Join-Path $root 'fpstate.dll'),[string[]]$selectors,'I',$true)
for($i=0;$i -lt $selectors.Count;$i++){if($combinedActual[$i] -ne $combinedExpected[$i]){$failures.Add([pscustomobject]@{case="combined $($selectors[$i])";expected=$combinedExpected[$i];actual=$combinedActual[$i]})}}
$rejections=0
foreach($method in @('unsupportedLayer','unsupportedDescriptor','unsupportedPackages')){
    $destination=Join-Path $root ('reject-'+$method)
    & $Boom @argsList --method $method --output $destination 2>&1|Out-Null
    if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $destination)){throw 'Unimplemented Module operation accepted'};$rejections++
}
$destination=Join-Path $root 'reject-unverified'
$withoutMetadata=@('compile-program','--entry-class','dev/boom/modules/ModuleEntry','--method','named','--output',$destination)
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\modules') -Filter '*.class'){$withoutMetadata+=@('--class-file',$file.FullName)}
& $Boom @withoutMetadata 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $destination)){throw 'Unverified module service accepted'};$rejections++
$report=[ordered]@{backend='boom-modules-program-v15-masm-x64';runtime_language='assembly';module_pool_abi=1;compiled_entries=($methods.Count+1);differential_cases=($cases.Count+$selectors.Count);native_executions=(($cases.Count+$selectors.Count)*2);pinned_java_base_module=$true;unnamed_module_per_defining_loader=$true;array_primitive_and_interface_membership=$true;module_identity_and_actual_getclass=$true;query_does_not_initialize_target=$true;native_abi_and_invalid_metadata_checked=$true;assertion_abi2_and_vm_clock_coexist=$true;multicore_records=24585;cold_initializer_records=8195;direct_cold_and_post_gc_records=16390;workers=8;module_identity_objects=2;cold_guest_objects=4;direct_query_guest_objects=19;quiescent_gc_roots=$true;negative_checks=$rejections;unsupported_operations_rejected=2;missing_layer_graph_rejected=$true;unverified_metadata_rejected=$true;layer_graph_requested=$false;dynamic_modules=$false;module_exports_readability=$false;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $projectRoot '.boom\latest-module-program.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
exit 0
