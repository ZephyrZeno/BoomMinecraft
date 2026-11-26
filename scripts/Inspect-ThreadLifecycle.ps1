param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/thread-lifecycle-inspections/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$entries=@(@('constructor','<init>','(Ljava/lang/ThreadGroup;Ljava/lang/String;ILjava/lang/Runnable;JLjava/security/AccessControlContext;)V'),@('run','run','()V'),@('start','start','()V'),@('exit','exit','()V'))
$attempts=@(foreach($entry in $entries){
    $log=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/Thread --method $entry[1] --descriptor $entry[2] --output (Join-Path $root $entry[0]) --assemble 2>&1|ForEach-Object ToString)-join "`n"
    $code=$LASTEXITCODE
    [IO.File]::WriteAllText((Join-Path $root ($entry[0]+'.txt')),$log,[Text.UTF8Encoding]::new($false))
    Write-Host ($entry[0]+': '+$code)
    [ordered]@{method=$entry[1];descriptor=$entry[2];compiler_exit_code=$code;compilation_complete=$code -eq 0;executed=$false;reason=$log}
})
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Thread lifecycle inspection compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;inspection_only=$true;attempts=$attempts;full_game_ready=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-thread-lifecycle-inspection.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
