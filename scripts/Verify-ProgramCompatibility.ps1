param([string]$PreviousReceipt='.boom/releases/v29/distribution-verification.json',[string]$Boom='dist/boom.exe')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$previous=Get-Content $PreviousReceipt -Raw|ConvertFrom-Json
$root=Join-Path (Get-Location) ('.boom/legacy-program-compatibility/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$checks=[Collections.Generic.List[object]]::new()
function Key($p){$entry=@($p.symbols|Where-Object id -eq $p.entry_id)[0];$entry.class_name+'|'+$entry.method+'|'+$entry.descriptor}
function VerifyArtifact($p){
    if($p.full_game_ready -or (Get-FileHash $p.compilation.assembly).Hash.ToLowerInvariant() -ne $p.compilation.assembly_digest.sha256 -or (Get-FileHash $p.compilation.dll).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256){throw 'Program artifact changed'}
    foreach($s in $p.sources){if((Get-FileHash $s.path).Hash.ToLowerInvariant() -ne $s.digest.sha256){throw 'Program source changed'}}
}
$pointers=[ordered]@{throwable_program='.boom/latest-throwable-program.txt';stream_fields_program='.boom/latest-stream-fields-program.txt';initialization_program='.boom/latest-initialization-program.txt';descriptor_program='.boom/latest-descriptor-program.txt';values_program='.boom/latest-values-program.txt'}
foreach($name in $pointers.Keys){
    $old=@{}
    foreach($file in Get-ChildItem (Split-Path $previous.reports_verified.$name) -Filter program.json -Recurse){$p=Get-Content $file.FullName -Raw|ConvertFrom-Json;if($p.schema -le 29){$old[(Key $p)]=@($p,$file.FullName)}}
    $folder=(Get-Content $pointers[$name] -Raw).Trim();$report=Get-Content (Join-Path $folder 'result.json') -Raw|ConvertFrom-Json
    if(-not $report.passed -or $report.compiler_sha256 -ne $sha -or $report.full_game_ready){throw 'Current compatibility report is not from this compiler'}
    $found=0
    foreach($file in Get-ChildItem $folder -Filter program.json -Recurse){
        $q=Get-Content $file.FullName -Raw|ConvertFrom-Json;if($q.schema -gt 29){continue};$key=Key $q
        if(-not $old.ContainsKey($key)){throw "Legacy reference not found: $key"};$p=$old[$key][0]
        VerifyArtifact $p;VerifyArtifact $q
        if($p.input_fingerprint -ne $q.input_fingerprint -or $p.compilation.assembly_digest.sha256 -ne $q.compilation.assembly_digest.sha256){throw "Legacy input identity or generated assembly changed: $key"}
        $checks.Add([ordered]@{entry=$key;profile=$q.schema;prior_program=$old[$key][1];current_program=$file.FullName;input_fingerprint=$q.input_fingerprint;assembly_sha256=$q.compilation.assembly_digest.sha256;unchanged=$true});$found++
    }
    if($found -ne $old.Count -or $found -ne $report.compiled_entries){throw "Legacy comparison count mismatch: $name"}
}
if($checks.Count -ne 29 -or (Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Compatibility scope or compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;prior_compiler_sha256=$previous.release_sha256;compared_programs=$checks.Count;input_identity_and_generated_assembly_unchanged=$true;checks=@($checks.ToArray());passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 9
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-legacy-compatibility.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output "Verified $($checks.Count) unchanged legacy inputs and generated assembly: $root"
exit 0
