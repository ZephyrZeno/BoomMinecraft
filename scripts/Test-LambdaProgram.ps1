param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='',[string]$BaselineBoom='')
$ErrorActionPreference='Stop'
$compilerSha256=(Get-FileHash -LiteralPath $Boom).Hash.ToLowerInvariant()
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
$root=Join-Path $projectRoot ('.boom\lambda-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/lambdas/LambdaEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Lambda original reference javac failed'}
& scripts/Build-FpProbe.ps1 -Output $root
& scripts/Build-AssemblyRuntime.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/LambdaProbe.cs
$argsList=@('compile-program','--entry-class','dev/boom/lambdas/LambdaEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
$files=@(Get-ChildItem (Join-Path $classes 'dev/boom/lambdas') -Filter '*.class')
foreach($file in $files){$argsList+=@('--class-file',$file.FullName)}
$methods=@('stateless','capture','bound','unbound','constructor','virtual','interfaceRef','defaultRef','widen','widenResult','wideCapture','doubleCapture','mixed','references','genericCast','badCast','discard','nullBound','nullUnbound','nullableCapture','narrow','cached','special','staticInterface')
$programs=@{}
foreach($method in $methods){
    $text=& $Boom @argsList --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Lambda compilation failed: $method; output: $root"}
    $p=$text|ConvertFrom-Json;$programs[$method]=$p
    if($p.schema -ne 17 -or $p.lambda_sites.Count -eq 0 -or $p.full_game_ready){throw 'Lambda program contract mismatch'}
    foreach($source in $p.sources){
        if($source.origin.generated){
            $proof=$source.origin.generated;$creatorSource=@($p.sources|Where-Object class_name -eq $proof.host_class)[0]
            if($proof.generator -ne 'boom-lambda' -or $proof.abi -ne 1 -or $proof.host_sha256 -ne $creatorSource.digest.sha256 -or $proof.host_loader -ne $creatorSource.origin.loader){throw 'Lambda creator source proof mismatch'}
        }elseif($source.origin.loader -eq 'explicit-application'){
            $original=Join-Path $classes ($source.class_name+'.class')
            if((Get-FileHash $original).Hash.ToLowerInvariant() -ne $source.digest.sha256){throw 'Original lambda input bytecode changed'}
        }
    }
    if((Get-FileHash $p.compilation.dll).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256){throw 'Lambda DLL changed'}
    Write-Output "Compiled lambda entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
$int=@('0','1','7f','80','ffff','ffffffff','80000000','7fffffff')
foreach($method in @('stateless','constructor','defaultRef','widen','widenResult','references','genericCast','badCast','discard','nullBound','nullUnbound','nullableCapture','cached','special','staticInterface')){foreach($a in $int){$cases.Add(@{method=$method;values=@($a)})}}
foreach($method in @('capture','bound','unbound','virtual','interfaceRef')){foreach($a in $int){foreach($b in $int){$cases.Add(@{method=$method;values=@($a,$b)})}}}
foreach($a in @('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','ffffffff00000000')){foreach($b in @('0','1','ffffffffffffffff','8000000000000000')){$cases.Add(@{method='wideCapture';values=@($a,$b)})}}
$double=@('0','8000000000000000','3ff0000000000000','bff0000000000000','1','7ff0000000000000','fff0000000000000','7ff8000000000001')
foreach($a in $double){foreach($b in $double){$cases.Add(@{method='doubleCapture';values=@($a,$b)})}}
foreach($a in $int){$cases.Add(@{method='mixed';values=@($a,'8000000000000001','c0200000','400c000000000000','ffffffff')});$cases.Add(@{method='narrow';values=@($a,$a,$a,$a,'80000000')})}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Lambda JVM oracle failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@('dev.boom.lambdas.LambdaEntry',$_.method,$programs[$_.method].compilation.descriptor)+$_.values) -join ' '})
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Lambda oracle input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Lambda JVM oracle timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Lambda oracle count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$p=$programs[$method]
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,$p.compilation.descriptor[-1],$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
if($failures.Count){$failures|ConvertTo-Json -Depth 8|Set-Content (Join-Path $root 'failures.json');throw "Lambda differential mismatches: $($failures.Count), $root"}
[BoomLambdaProbe]::Parallel($programs['capture'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),0,0,0)
$cached=@($programs['cached'].classes|Where-Object name -eq 'dev/boom/lambdas/Cached')[0];$count=@($cached.fields|Where-Object name -eq count)[0]
[BoomLambdaProbe]::Parallel($programs['cached'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),1,$cached.id,$count.index)
[BoomLambdaProbe]::Parallel($programs['stateless'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),3,0,0)
$allocationComparison=$null
if($BaselineBoom){
    $text=& $BaselineBoom @argsList --method stateless --output (Join-Path $root 'stateless-baseline')
    if($LASTEXITCODE -ne 0){throw 'Stateless allocation baseline compilation failed'};$baseline=$text|ConvertFrom-Json
    $current=$programs['stateless']
    foreach($source in $current.sources|Where-Object {-not $_.origin.generated}){
        $previous=@($baseline.sources|Where-Object class_name -eq $source.class_name)[0]
        if($previous.digest.sha256 -ne $source.digest.sha256){throw 'Stateless baseline original inputs differ'}
    }
    [BoomLambdaProbe]::Parallel($baseline.compilation.dll,(Join-Path $root 'boom-runtime.dll'),2,0,0)
    $allocationComparison=@{scope='One stateless call site, three batches of 8195 invocations, 8 ASM workers; not whole-game memory or pause performance';original_sources_equal=$true;baseline_compiler_sha256=(Get-FileHash $BaselineBoom).Hash.ToLowerInvariant();baseline_guest_allocations=24585;optimized_guest_allocations=1;baseline_reclaimed_objects=24585;optimized_reclaimed_objects=0;optimized_rooted_closures=1}
}
$rejections=0
$collisionName=($programs['capture'].lambda_sites[0].class_name -split '/')[-1]
$collisionSource=Join-Path $root ($collisionName+'.java')
[IO.File]::WriteAllText($collisionSource,('package dev.boom.lambdas; final class '+$collisionName+' {}'),[Text.UTF8Encoding]::new($false))
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes $collisionSource
if($LASTEXITCODE -ne 0){throw 'Collision fixture javac failed'}
$collisionOutput=Join-Path $root 'reject-name-collision'
& $Boom @argsList --class-file (Join-Path $classes ('dev/boom/lambdas/'+$collisionName+'.class')) --method capture --output $collisionOutput 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $collisionOutput)){throw 'Input class collision acquired compiler-generated privileges'};$rejections++
foreach($method in @('alternate')){
    $destination=Join-Path $root ('reject-'+$method);& $Boom @argsList --method $method --output $destination 2>&1|Out-Null
    if($LASTEXITCODE -eq 0 -or (Test-Path $destination)){throw 'Unsupported lambda alternate bootstrap accepted'};$rejections++
}
$without=@('compile-program','--entry-class','dev/boom/lambdas/LambdaEntry','--method','capture','--output',(Join-Path $root 'reject-unverified'))
foreach($file in $files){$without+=@('--class-file',$file.FullName)}
& $Boom @without 2>&1|Out-Null;if($LASTEXITCODE -eq 0 -or (Test-Path (Join-Path $root 'reject-unverified'))){throw 'Unverified lambda accepted'};$rejections++
$report=[ordered]@{backend='boom-lambda-program-v17-masm-x64';runtime_language='assembly';compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=(8195*9);baseline_multicore_records=if($BaselineBoom){8195*3}else{0};workers=8;original_bytecode_unchanged=$true;compiler_provenance=$true;capture_reference_gc=$true;statics_initialized_once=$true;stateless_singleton=$true;allocation_comparison=$allocationComparison;negative_checks=$rejections;alternate_metafactory=$false;general_method_handles=$false;automatic_gc=$false;passed=$true;full_game_ready=$false;run_directory=$root}
if((Get-FileHash -LiteralPath $Boom).Hash.ToLowerInvariant() -ne $compilerSha256){throw 'Lambda compiler changed during verification'}
$report.compiler_sha256=$compilerSha256
$json=$report|ConvertTo-Json -Depth 8;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-lambda-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
