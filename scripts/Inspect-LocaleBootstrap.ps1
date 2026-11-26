param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/locale-bootstrap-inspections/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/casing/LocaleBootstrap.java
if($LASTEXITCODE -ne 0){throw 'Locale inspection javac failed'}
$attempts=@(foreach($method in @('root','systemDefault')){
    $text=& $Boom compile-program --class-file (Join-Path $classes 'dev/boom/casing/LocaleBootstrap.class') --entry-class dev/boom/casing/LocaleBootstrap --method $method --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root $method) --assemble 2>&1
    $code=$LASTEXITCODE;$log=($text|ForEach-Object ToString)-join "`n"
    [IO.File]::WriteAllText((Join-Path $root ($method+'.txt')),$log,[Text.UTF8Encoding]::new($false))
    [ordered]@{method=$method;compiler_exit_code=$code;compilation_complete=$code -eq 0;Locale_initialization_executed=$false;reason=if($code -eq 0){'Compilation completed; this inspection does not execute Locale initialization.'}else{$log}}
})
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Locale inspection compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;inspection_only=$true;attempts=$attempts;full_game_ready=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-locale-bootstrap.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
