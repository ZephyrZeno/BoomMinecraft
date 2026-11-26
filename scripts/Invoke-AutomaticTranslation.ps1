param(
    [Parameter(Mandatory=$true)][string]$Pipeline,
    [Parameter(Mandatory=$true)][string]$Lock,
    [string]$Boom='target/release/boom.exe',
    [string]$Python='D:/Dev/Python312/python.exe',
    [ValidateRange(1,64)][int]$Workers=8,
    [string]$ResumeBatch,
    [string[]]$Entry,
    [string[]]$ClassRoot,
    [switch]$DirectOnly,
    [string]$PreviousWorklist,
    [switch]$Force
)
$ErrorActionPreference='Stop'
if($DirectOnly -and -not ($Entry.Count -or $ClassRoot.Count)){throw '-DirectOnly requires an entry or class root'}
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pipelinePath=(Resolve-Path -LiteralPath $Pipeline).Path
$lockPath=(Resolve-Path -LiteralPath $Lock).Path
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$pythonPath=(Resolve-Path -LiteralPath $Python).Path
$inputs=Get-Content -LiteralPath $pipelinePath -Raw|ConvertFrom-Json
foreach($field in @('side','catalog','plan','ir')){
    if(-not $inputs.$field){throw "Pipeline is missing $field"}
}
if($inputs.side -notin @('server','client')){throw 'Pipeline side must be server or client'}
# No account, world, original input, or launcher directory is modified.
$identity=[ordered]@{schema=3;side=$inputs.side;workers_affect_cache=$false;entry=@($Entry);class_root=@($ClassRoot);direct_only=[bool]$DirectOnly}
$sourceFiles=@($boomPath,$lockPath,$inputs.catalog,(Join-Path $inputs.plan 'summary.json'),(Join-Path $inputs.ir 'summary.json'),$PSCommandPath)
$sourceFiles+=@(Get-ChildItem -LiteralPath $PSScriptRoot -File|Where-Object{$_.Name -like 'verify-batch-*.py' -or $_.Name -in @('verify-string-literal-module.py','summarize-translation-gaps.py')}|Sort-Object Name|ForEach-Object FullName)
$sourceFiles+=(Join-Path $project 'native/kernels/batch_virtual_dispatch.inc')
$sourceFiles+=@(Get-ChildItem -LiteralPath (Join-Path $project 'native/runtime') -File -Filter '*.asm'|Sort-Object Name|ForEach-Object FullName)
$sourceFiles+=@('plan-translation-completion.py','plan-protocol-expansion.py','prepare-class-init-probe.py','batch-source.py','select-batch-dispatch.py')|ForEach-Object{Join-Path $PSScriptRoot $_}
if($PreviousWorklist){$sourceFiles+=(Resolve-Path -LiteralPath $PreviousWorklist).Path}
$hashes=[ordered]@{}
foreach($file in $sourceFiles){$path=(Resolve-Path -LiteralPath $file).Path;$hashes[$path]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
$identity['files']=$hashes
$identityJson=$identity|ConvertTo-Json -Depth 5 -Compress
$sha=[Security.Cryptography.SHA256]::Create()
try{$key=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($identityJson)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
$cache=Join-Path $project ('.boom/automatic-translation/'+$inputs.side+'/'+$key)
[IO.Directory]::CreateDirectory($cache)|Out-Null
$pointer=Join-Path $cache 'cache.json'
$utf8=[Text.UTF8Encoding]::new($false)
$artifactRoot=[IO.Path]::GetFullPath((Join-Path $project '.boom'))+[IO.Path]::DirectorySeparatorChar
$expectedLock=Get-Content -LiteralPath $lockPath -Raw|ConvertFrom-Json
$expectedIR=Get-Content -LiteralPath (Join-Path $inputs.ir 'summary.json') -Raw|ConvertFrom-Json
function Confirm-BatchIdentity([string]$Candidate){
    if(-not $Candidate.StartsWith($artifactRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Reusable batch must be inside this project .boom directory'}
    $candidateSummary=Get-Content -LiteralPath (Join-Path $Candidate 'summary.json') -Raw|ConvertFrom-Json
    if($candidateSummary.compiler_sha256 -ne $hashes[$boomPath] -or $candidateSummary.input_fingerprint -ne $expectedLock.fingerprint -or $candidateSummary.ir_identity -ne $expectedIR.identity){throw 'Reusable batch compiler/lock/IR identity differs'}
    foreach($flag in @('linked','runtime_abi_verified','module_access_verified','game_started','world_created','full_game_ready')){if($candidateSummary.$flag -ne $false){throw "Unexpected reusable batch state: $flag"}}
}
function Invoke-CheckedTool([string]$Executable,[string[]]$Arguments,[string]$Prefix){
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$Executable;$start.WorkingDirectory=$project
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($argument in $Arguments){$start.ArgumentList.Add($argument)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start
    try{
        if(-not $process.Start()){throw 'Cannot start translation tool'}
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        $process.WaitForExit();$stdout=$out.GetAwaiter().GetResult();$stderr=$err.GetAwaiter().GetResult()
        [IO.File]::WriteAllText($Prefix+'.out.log',$stdout,$utf8)
        [IO.File]::WriteAllText($Prefix+'.err.log',$stderr,$utf8)
        if($process.ExitCode -ne 0){throw "Tool failed with exit $($process.ExitCode); inspect $Prefix.err.log"}
    }finally{$process.Dispose()}
}
$session=Join-Path $cache ([guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($session)|Out-Null
Invoke-CheckedTool $boomPath @('verify','--lock',$lockPath) (Join-Path $session 'locked-inputs')
$batch=$null;$cacheReused=$false;$resumedBatch=$false
if($ResumeBatch){
    $batch=[IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ResumeBatch).Path)
    Confirm-BatchIdentity $batch
    Write-Host 'Resuming independent verification of existing translation artifacts...'
    Invoke-CheckedTool $pythonPath @((Join-Path $PSScriptRoot 'verify-batch-assembly.py'),$batch,'--plan',$inputs.plan,'--ir',$inputs.ir,'--output',(Join-Path $batch 'verification.json')) (Join-Path $session 'resumed-verification')
    $resumedBatch=$true
}
if(-not $batch -and -not $Force -and (Test-Path -LiteralPath $pointer)){
    $previous=Get-Content -LiteralPath $pointer -Raw|ConvertFrom-Json
    $candidate=[IO.Path]::GetFullPath([string]$previous.batch)
    if($previous.key -eq $key -and $candidate.StartsWith($artifactRoot,[StringComparison]::OrdinalIgnoreCase)){
        try{
            Confirm-BatchIdentity $candidate
            Write-Host 'Checking cached assembly, source contracts, and COFF objects...'
            Invoke-CheckedTool $pythonPath @((Join-Path $PSScriptRoot 'verify-batch-assembly.py'),$candidate,'--plan',$inputs.plan,'--ir',$inputs.ir,'--output',(Join-Path $candidate 'verification.json')) (Join-Path $session 'cache-verification')
            $batch=$candidate;$cacheReused=$true
        }catch{
            Write-Host 'Cached output failed verification; generating a fresh isolated output.'
        }
    }
}
if(-not $batch){
    $batch=Join-Path $session 'batch'
    Write-Host "Generating Java MASM, metadata, and shared dispatch contracts with $Workers workers..."
    Invoke-CheckedTool $boomPath @('compile-translation','--lock',$lockPath,'--jdk-base',$inputs.catalog,'--ir',$inputs.ir,'--workers',"$Workers",'--assemble','--output',$batch) (Join-Path $session 'compile')
    Invoke-CheckedTool $pythonPath @((Join-Path $PSScriptRoot 'verify-batch-assembly.py'),$batch,'--plan',$inputs.plan,'--ir',$inputs.ir,'--output',(Join-Path $batch 'verification.json')) (Join-Path $session 'verification')
}
Invoke-CheckedTool $pythonPath @((Join-Path $PSScriptRoot 'summarize-translation-gaps.py'),$batch,'--output',(Join-Path $batch 'compatibility-summary.json')) (Join-Path $session 'compatibility')
$completionArguments=@((Join-Path $PSScriptRoot 'plan-translation-completion.py'),$batch,'--plan',$inputs.plan,'--output',(Join-Path $session 'completion-worklist.json'))
if($Entry.Count -or $ClassRoot.Count){
    $scan=Join-Path $session 'entry-scan'
    $scanArguments=@((Join-Path $PSScriptRoot 'prepare-class-init-probe.py'),$batch,'--plan',$inputs.plan,'--output',$scan,'--scan')
    foreach($root in $ClassRoot){$scanArguments+=@('--class-root',$root)}
    foreach($method in $Entry){$scanArguments+=@('--entry',$method)}
    if($DirectOnly){$scanArguments+='--direct-only'}
    Invoke-CheckedTool $pythonPath $scanArguments (Join-Path $session 'entry-scan')
    $completionArguments+=@('--frontiers',(Join-Path $scan 'frontiers.json'))
}
if($PreviousWorklist){$completionArguments+=@('--previous',(Resolve-Path -LiteralPath $PreviousWorklist).Path)}
Invoke-CheckedTool $pythonPath $completionArguments (Join-Path $session 'completion')
# Plan actual source shapes once per verified batch. This produces design data,
# not implementations, and cannot promote a pending contract to a provider.
$protocolPlan=Join-Path $session 'protocol-expansion'
Invoke-CheckedTool $pythonPath @((Join-Path $PSScriptRoot 'plan-protocol-expansion.py'),$batch,'--ir',$inputs.ir,'--workers',"$([Math]::Min($Workers,16))",'--output',$protocolPlan) (Join-Path $session 'protocol-expansion')
foreach($path in $hashes.Keys){if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hashes[$path]){throw "Translation input/tool changed during run: $path"}}
$batchSummary=Get-Content -LiteralPath (Join-Path $batch 'summary.json') -Raw|ConvertFrom-Json
$implementedRules=@()
if($batchSummary.schema -ge 14 -and $batchSummary.string_concat.generated_sites -gt 0){$implementedRules+='java/lang/invoke/StringConcatFactory:supported_shapes'}
$result=[ordered]@{schema=3;key=$key;side=$inputs.side;batch=$batch;cache_reused=$cacheReused;resumed_batch=$resumedBatch;source_identity=$identity;verified=$true;compatibility_report=(Join-Path $batch 'compatibility-summary.json');completion_worklist=(Join-Path $session 'completion-worklist.json');protocol_expansion_plan=(Join-Path $protocolPlan 'summary.json');protocol_expanders_implemented=($implementedRules.Count -gt 0);implemented_protocol_rules=$implementedRules;all_protocol_expanders_implemented=$false;linked=$false;game_started=$false;world_created=$false;full_game_ready=$false}
$json=$result|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $session 'result.json'),$json,$utf8)
$temporary=Join-Path $cache ('cache-'+[guid]::NewGuid().ToString('N')+'.tmp')
[IO.File]::WriteAllText($temporary,$json,$utf8);Move-Item -LiteralPath $temporary -Destination $pointer -Force
Write-Output $json
