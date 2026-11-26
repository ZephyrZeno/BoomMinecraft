param([string]$ClientLock='.boom\locks\client.json',[string]$ServerLock='.boom\locks\server.json',[string]$Boom='target\release\boom.exe',[string]$ClientJdkBase='',[string]$ServerJdkBase='',[string]$ClientJdkModules='',[string]$ServerJdkModules='')
$ErrorActionPreference='Stop'
$compilerSha=(Get-FileHash -LiteralPath $Boom).Hash.ToLowerInvariant()
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
# Reuse the project-isolated, verified inputs when the caller omits manifests.
function PreparedManifest([string]$value,[string]$pointer,[string]$file){
    if($value){return $value}
    $path=Join-Path $projectRoot $pointer
    if(Test-Path -LiteralPath $path){return Join-Path ((Get-Content -LiteralPath $path -Raw).Trim()) $file}
    return ''
}
$ClientJdkBase=PreparedManifest $ClientJdkBase '.boom/latest-jdk-base.txt' 'jdk-base.json'
$ServerJdkBase=PreparedManifest $ServerJdkBase '.boom/latest-server-jdk-base.txt' 'jdk-base.json'
$ClientJdkModules=PreparedManifest $ClientJdkModules '.boom/latest-jdk-modules.txt' 'jdk-modules.json'
$ServerJdkModules=PreparedManifest $ServerJdkModules '.boom/latest-server-jdk-modules.txt' 'jdk-modules.json'
$root=Join-Path $projectRoot ('.boom\startup-attempts\'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$attempts=[Collections.Generic.List[object]]::new()
foreach($side in @('client','server')){
    $lockPath=if($side -eq 'client'){$ClientLock}else{$ServerLock}
    $inputs=Get-Content -LiteralPath $lockPath -Raw|ConvertFrom-Json
    $entry=$inputs.main_class.Replace('.','/')
    $output=Join-Path $root $side
    $metadataArgs=@();$manifest=if($side -eq 'client'){$ClientJdkBase}else{$ServerJdkBase}
    if($manifest){$metadataArgs=@('--jdk-base',$manifest)}
    $moduleManifest=if($side -eq 'client'){$ClientJdkModules}else{$ServerJdkModules}
    if($moduleManifest){$metadataArgs+=@('--jdk-modules',$moduleManifest)}
    $text=& $Boom compile-locked-program --lock $lockPath --entry-class $entry --method main --descriptor '([Ljava/lang/String;)V' --output $output --assemble @metadataArgs 2>&1
    $code=$LASTEXITCODE;$log=($text|ForEach-Object ToString) -join "`n"
    [IO.File]::WriteAllText((Join-Path $root ($side+'.txt')),$log,[Text.UTF8Encoding]::new($false))
    $attempts.Add([pscustomobject]@{side=$side;entry=$entry;descriptor='([Ljava/lang/String;)V';input_fingerprint=$inputs.fingerprint;jdk_base_manifest=$manifest;jdk_module_manifest=$moduleManifest;compiler_exit_code=$code;compilation_complete=$code -eq 0;game_started=$false;reason=if($code -eq 0){'Compilation completed; this inspection does not execute a game.'}else{$log}})
}
if((Get-FileHash -LiteralPath $Boom).Hash.ToLowerInvariant() -ne $compilerSha){throw 'Entry inspection compiler changed during the run'}
$report=[ordered]@{backend='own-assembly';compiler_sha256=$compilerSha;inspection_only=$true;attempts=@($attempts.ToArray());full_game_ready=$false;world_created=$false;jvm_fallback=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-startup-attempt.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
