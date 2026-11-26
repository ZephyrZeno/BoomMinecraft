param([string]$MetadataLock='.boom/locks/server.json')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/finalization-policy-oracle-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
foreach($file in $inputs.java.runtime_files){if((Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Locked oracle runtime changed'}}
$classes=Join-Path $root classes;$source=Join-Path $project 'java/reference/FinalizationPolicyReference.java'
& (Join-Path ([IO.Path]::GetDirectoryName($inputs.java.executable)) 'javac.exe') --release 21 -g:none -proc:none -encoding UTF-8 -d $classes $source
if($LASTEXITCODE -ne 0){throw 'Finalization policy oracle compilation failed'}
$results=@()
foreach($mode in @('default','enabled','disabled')){
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$inputs.java.executable;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$start.Environment.Remove($key)|Out-Null}
    foreach($arg in @('-Xmx64m','--add-opens','java.base/java.lang.ref=ALL-UNNAMED')){$start.ArgumentList.Add($arg)}
    if($mode -ne 'default'){$start.ArgumentList.Add('--finalization='+$mode)}
    foreach($arg in @('-cp',$classes,'FinalizationPolicyReference')){$start.ArgumentList.Add($arg)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start
    try{
        if(-not $process.Start()){throw 'Oracle process failed to start'}
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(15000)){throw 'Oracle timed out'}
        $value=$out.GetAwaiter().GetResult().Trim();$errors=$err.GetAwaiter().GetResult()
        if($process.ExitCode -ne 0 -or $value -notin @('true','false')){throw ('Oracle query failed: '+$errors)}
        $enabled=$value -eq 'true';if($enabled -ne ($mode -ne 'disabled')){throw 'Original finalization policy differs from expected VM configuration'}
        $results+=[ordered]@{mode=$mode;enabled=$enabled}
    }finally{if(-not $process.HasExited){$process.Kill($true);$process.WaitForExit()};$process.Dispose()}
}
foreach($file in $inputs.java.runtime_files){if((Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Oracle runtime changed during execution'}}
$result=[ordered]@{passed=$true;scope='locked_JVM_finalization_policy_reference_only';cases=$results;metadata_lock_sha256=(Get-FileHash -LiteralPath $MetadataLock -Algorithm SHA256).Hash.ToLowerInvariant();java_executable_sha256=(Get-FileHash -LiteralPath $inputs.java.executable -Algorithm SHA256).Hash.ToLowerInvariant();runtime_file_count=$inputs.java.runtime_files.Count;script_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();source_sha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant();class_sha256=(Get-FileHash -LiteralPath (Join-Path $classes 'FinalizationPolicyReference.class') -Algorithm SHA256).Hash.ToLowerInvariant();assembly_query_executed=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $project '.boom/latest-finalization-policy-oracle.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
