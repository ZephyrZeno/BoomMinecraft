param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/object-string-inspections/'+[guid]::NewGuid().ToString('N'));$classes=Join-Path $root classes;[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/hex/ObjectStringProbe.java
if($LASTEXITCODE -ne 0){throw 'Object string discovery javac failed'}
$attempts=@(foreach($method in @('defaultObject','classObject')){
    $text=& $Boom compile-program --class-file (Join-Path $classes dev/boom/hex/ObjectStringProbe.class) --entry-class dev/boom/hex/ObjectStringProbe --method $method --descriptor '(I)Ljava/lang/String;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root $method) --assemble 2>&1
    $code=$LASTEXITCODE;$log=($text|ForEach-Object ToString)-join "`n";[IO.File]::WriteAllText((Join-Path $root ($method+'.txt')),$log,[Text.UTF8Encoding]::new($false))
    [ordered]@{method=$method;compiler_exit_code=$code;compilation_complete=$code -eq 0;native_execution_verified=$false;reason=if($code -eq 0){'Compiled only; this inspection does not execute the program.'}else{$log}}
})
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Object string inspection compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;inspection_only=$true;attempts=$attempts;Object_toString_complete=$false;full_game_ready=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-object-string-inspection.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
