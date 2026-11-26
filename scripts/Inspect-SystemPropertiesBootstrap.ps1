param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/system-property-bootstrap-inspections/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$entries=@(@('jdk/internal/util/SystemProps','initProperties','()Ljava/util/Map;'),@('jdk/internal/util/StaticProperty','javaHome','()Ljava/lang/String;'))
$attempts=@(foreach($entry in $entries){
    $text=& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class $entry[0] --method $entry[1] --descriptor $entry[2] --output (Join-Path $root $entry[1]) --assemble 2>&1
    $code=$LASTEXITCODE;$log=($text|ForEach-Object ToString)-join "`n"
    [IO.File]::WriteAllText((Join-Path $root ($entry[1]+'.txt')),$log,[Text.UTF8Encoding]::new($false))
    [ordered]@{class=$entry[0];method=$entry[1];compiler_exit_code=$code;compilation_complete=$code -eq 0;Java_System_property_bootstrap_executed=$false;reason=if($code -eq 0){'Compilation completed; inspection does not execute Java System startup.'}else{$log}}
})
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Property bootstrap inspection compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;inspection_only=$true;attempts=$attempts;full_game_ready=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-system-property-bootstrap.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
