param([string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$root=Join-Path $projectRoot ('.boom\string-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\strings') -Filter '*.java' -File|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'String program reference javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$baseArgs=@('compile-program','--entry-class','dev/boom/strings/StringEntry','--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\strings') -Filter '*.class' -File){$baseArgs+=@('--class-file',$file.FullName)}
$methods=@('length','empty','character','hash','equal','compare','identity','intern','toStringIdentity','notString','equalsNull','nullReceiver','nullCharacter','nullOther','array','nullElement','state','hashMix')
$programs=@{};$manifests=@{}
foreach($method in ($methods+@('failure'))){
    $text=& $boomPath @baseArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "String program compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
    if($program.schema -ne 4 -or $program.bootstrap_string_abi -ne 2 -or -not $program.bootstrap_string_runtime -or -not $program.compilation.requires_heap){throw 'Unexpected String runtime compilation contract.'}
}
if($programs['identity'].string_literals.Count -ne 8){throw 'Equal literals in separate classes were not deduplicated.'}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$value){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
function AddCase([string]$method,[string[]]$values){$cases.Add([pscustomobject]@{method=$method;values=$values})}
foreach($which in @(-1,0,1,2,3,4,5,6,7,8,[int]::MinValue,[int]::MaxValue)){
    foreach($method in @('length','empty','hash','identity','intern','toStringIdentity','notString','equalsNull','nullReceiver','nullOther','state')){AddCase $method @((Bits $which))}
    foreach($index in @(-1,0,1,2,3,4,5,6,[int]::MinValue,[int]::MaxValue)){AddCase 'character' @((Bits $which),(Bits $index));AddCase 'nullCharacter' @((Bits $which),(Bits $index))}
    AddCase 'hashMix' @((Bits $which),'80000000')
}
foreach($a in 0..7){foreach($b in 0..7){AddCase 'equal' @((Bits $a),(Bits $b));AddCase 'compare' @((Bits $a),(Bits $b))}}
foreach($count in @(-1,0,1,2,7,17)){
    foreach($index in @(-1,0,1,($count-1),$count)){foreach($method in @('array','nullElement')){AddCase $method @((Bits $count),(Bits $index))}}
}
AddCase 'failure' @();AddCase 'failure' @()
$lines=@($cases|ForEach-Object{(@('dev.boom.strings.StringEntry',$_.method,$manifests[$_.method].descriptor)+@($_.values)) -join ' '})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'String JVM reference failed to start.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'String JVM reference input stalled.'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'String JVM reference timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'String reference case count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'String module identity mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$rejections=0
foreach($method in @('unsupportedConstructor','unsupportedMethod')){
    $destination=Join-Path $root ('reject-'+$method)
    & $boomPath @baseArgs --method $method --output $destination 2>&1|Out-Null
    if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $destination)){throw 'Unsupported String operation was accepted.'};$rejections++
}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\StringProgramProbe.cs')
$hashIndex=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq 'hashMix' -and $cases[$i].values[0] -eq '0'){$i}})[0]
$expectedHash=[uint32]([Convert]::ToUInt64($expected[$hashIndex].Substring(2),16) -bxor [uint64]2147483648)
[BoomStringProgramProbe]::Cold($manifests['hashMix'].dll,(Join-Path $root 'boom-runtime.dll'),$expectedHash)
$state=@($programs['state'].classes|Where-Object name -eq 'dev/boom/strings/TextState')[0]
function StaticFieldIndex([string]$name){$field=@($state.fields|Where-Object name -eq $name);if($field.Count -ne 1){throw 'Missing String state field'};return [uint32]$field[0].index}
[BoomStringProgramProbe]::Constants($manifests['state'].dll,$state.id,(StaticFieldIndex 'CONST'),(StaticFieldIndex 'text'),(StaticFieldIndex 'alias'),(StaticFieldIndex 'table'))
[BoomStringProgramProbe]::AbiAndFailure((Join-Path $root 'boom-runtime.dll'))
$failedClass=@($programs['failure'].classes|Where-Object name -eq 'dev/boom/strings/TextFailure')[0]
$actual=[BoomStringProgramProbe]::FailedInitializer($manifests['failure'].dll,$failedClass.id,$failedClass.initializer)
$failureIndices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq 'failure'){$i}})
for($n=0;$n -lt 2;$n++){if($actual[$n] -ne $expected[$failureIndices[$n]]){$failures.Add([pscustomobject]@{method='failure';expected=$expected[$failureIndices[$n]];actual=$actual[$n]})}}
$report=[ordered]@{backend='boom-string-program-v4-masm-x64';runtime_language='assembly';string_pool_abi=2;compiled_entries=$methods.Count+1;differential_cases=$cases.Count;native_executions=($cases.Count-2)*2+2;cold_literal_records=4099;cold_allocation_once=$true;utf16_and_modified_utf8=$true;nul_and_unpaired_surrogates=$true;cross_class_literal_identity=$true;hash_collision_values_distinct=$true;literal_gc_roots=$true;string_constant_value_preparation=$true;string_reference_arrays=$true;failed_initializer_preserves_prepared_strings=$true;native_partial_failure_and_heap_binding=$true;only_literal_string_instances=$true;dynamic_string_construction=$false;unsupported_operations_rejected=$rejections;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
