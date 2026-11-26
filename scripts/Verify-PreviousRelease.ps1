param([string]$PreviousReceipt='.boom/releases/v31/distribution-verification.json',[string]$Boom='target/release/boom.exe')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant();$receipt=Get-Content $PreviousReceipt -Raw|ConvertFrom-Json
$root=Join-Path (Get-Location) ('.boom/previous-release-checks/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$references=[Collections.Generic.List[string]]::new()
foreach($name in @('string_case_program','unwind_program')){foreach($f in Get-ChildItem (Split-Path $receipt.reports_verified.$name) -Filter program.json -Recurse){$references.Add($f.FullName)}}
$prior=Get-Content $receipt.reports_verified.prior_program_rebuilds -Raw|ConvertFrom-Json
foreach($check in $prior.checks){$references.Add($check.program)}
if($references.Count -ne 94){throw 'Previous release artifact scope changed'}
$unique=@{};$duplicates=[Collections.Generic.List[object]]::new()
foreach($path in $references){$p=Get-Content $path -Raw|ConvertFrom-Json;if((Get-FileHash $p.compilation.dll).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256 -or (Get-FileHash $p.compilation.assembly).Hash.ToLowerInvariant() -ne $p.compilation.assembly_digest.sha256){throw 'Prior program artifact changed'};$key=$p.input_fingerprint+'|'+$p.compilation.assembly_digest.sha256;if($unique.ContainsKey($key)){$duplicates.Add([ordered]@{duplicate=$path;equivalent=$unique[$key];input_fingerprint=$p.input_fingerprint;assembly_sha256=$p.compilation.assembly_digest.sha256})}else{$unique[$key]=$path}}
if($unique.Count -ne 70 -or $duplicates.Count -ne 24){throw 'Previous release equivalence scope changed'}
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root 'fp-build.log') 2>&1
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/UnwindProbe.cs
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json';$checks=[Collections.Generic.List[object]]::new();$calls=0
foreach($path in ($unique.Values|Sort-Object)){
    $p=Get-Content $path -Raw|ConvertFrom-Json;$entry=@($p.symbols|Where-Object id -eq $p.entry_id)[0];$out=Join-Path $root $checks.Count.ToString('d3')
    $a=@('compile-program','--entry-class',$entry.class_name,'--method',$entry.method,'--descriptor',$entry.descriptor,'--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--output',$out,'--assemble')
    foreach($s in $p.sources|Where-Object {$_.origin.loader -eq 'explicit-application' -and -not $_.origin.generated}){if((Get-FileHash $s.path).Hash.ToLowerInvariant() -ne $s.digest.sha256){throw 'Prior source changed'};$a+=@('--class-file',$s.path)}
    & $Boom @a > (Join-Path $root ($checks.Count.ToString('d3')+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw 'Previous release program rebuild failed'}
    $q=Get-Content (Join-Path $out 'program.json') -Raw|ConvertFrom-Json
    if($q.input_fingerprint -ne $p.input_fingerprint -or $q.compilation.assembly_digest.sha256 -ne $p.compilation.assembly_digest.sha256 -or $q.schema -ne $p.schema -or $null -ne $q.constructor_entry -or $null -ne $q.platform_properties){throw 'New VM entries changed prior input identity or emitted code'}
    if($entry.method -in @('uncaught','throwing')){$class=if($entry.method -eq 'uncaught'){'dev/boom/unwind/UnwindProgram$Child'}else{'java/lang/IllegalStateException'};$owner=@($q.classes|Where-Object name -eq $class)[0];[BoomUnwindProbe]::Uncaught($q.compilation.dll,$owner.id);$n=2}
    elseif($null -ne $q.exception_runtime){$before=[BoomUnwindProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),[uint32[]]@(0,1,2,4294967295));$after=[BoomUnwindProbe]::Run($q.compilation.dll,(Join-Path $root 'fpstate.dll'),[uint32[]]@(0,1,2,4294967295));if(($before -join '|') -ne ($after -join '|')){throw 'Prior Context32 behavior changed'};$n=12}
    else{$arity=@($p.compilation.signature.arguments).Count;[string[]]$values=@(foreach($v in @('0','1','ffffffff')){(@(for($i=0;$i -lt $arity;$i++){if($i -eq 0){$v}else{'0'}})) -join ' '});$type=$entry.descriptor[$entry.descriptor.Length-1];$before=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,$type,$true);$after=[BoomNumericProbe]::Run($q.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,$type,$true);if(($before -join '|') -ne ($after -join '|')){throw 'Prior native behavior changed'};$n=6}
    $calls+=$n;$checks.Add([ordered]@{prior_program=$path;program=(Join-Path $out 'program.json');entry=($entry.class_name+'.'+$entry.method+$entry.descriptor);profile=$q.schema;input_fingerprint=$q.input_fingerprint;assembly_sha256=$q.compilation.assembly_digest.sha256;unchanged=$true;current_native_executions=$n});Write-Output "Verified unchanged profile $($q.schema): $($entry.method)"
}
if($calls -ne 568 -or (Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Compatibility call scope/compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;prior_compiler_sha256=$receipt.release_sha256;reference_artifacts_checked=94;unique_program_rebuilds=70;equivalent_duplicates=24;current_native_executions=$calls;input_identity_and_generated_assembly_unchanged=$true;checks=@($checks.ToArray());duplicates=@($duplicates.ToArray());passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 9
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-previous-release-check.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output "Verified 94 prior artifacts, 70 unique rebuilt programs and 568 current native calls: $root"
exit 0
