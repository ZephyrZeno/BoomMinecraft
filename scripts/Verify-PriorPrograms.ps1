param([string]$PreviousReceipt='.boom/releases/v30/distribution-verification.json',[string]$Boom='dist/boom.exe')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$prior=Get-Content $PreviousReceipt -Raw|ConvertFrom-Json
$root=Join-Path (Get-Location) ('.boom/prior-program-rebuilds/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/UnwindProbe.cs
$checks=[Collections.Generic.List[object]]::new();$executions=0
foreach($name in @('unwind_program','throwable_program','stream_fields_program','initialization_program','descriptor_program','values_program')){
    $folder=Split-Path $prior.reports_verified.$name
    foreach($file in Get-ChildItem $folder -Filter program.json -Recurse){
        $p=Get-Content $file.FullName -Raw|ConvertFrom-Json
        if((Get-FileHash $p.compilation.assembly).Hash.ToLowerInvariant() -ne $p.compilation.assembly_digest.sha256 -or (Get-FileHash $p.compilation.dll).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256){throw 'Prior program artifact changed'}
        $entry=@($p.symbols|Where-Object id -eq $p.entry_id)[0];$out=Join-Path $root $checks.Count.ToString('d3')
        $a=@('compile-program','--entry-class',$entry.class_name,'--method',$entry.method,'--descriptor',$entry.descriptor,'--metadata-lock','.boom/locks/server.json','--jdk-base',$base,'--output',$out,'--assemble')
        foreach($s in $p.sources|Where-Object {$_.origin.loader -eq 'explicit-application' -and -not $_.origin.generated}){if((Get-FileHash $s.path).Hash.ToLowerInvariant() -ne $s.digest.sha256){throw 'Prior fixture source changed'};$a+=@('--class-file',$s.path)}
        & $Boom @a > (Join-Path $root ($checks.Count.ToString('d3')+'-compile.json'))
        if($LASTEXITCODE -ne 0){throw 'Prior program rebuild failed'}
        $q=Get-Content (Join-Path $out 'program.json') -Raw|ConvertFrom-Json
        if($p.input_fingerprint -ne $q.input_fingerprint -or $p.compilation.assembly_digest.sha256 -ne $q.compilation.assembly_digest.sha256 -or $p.schema -ne $q.schema -or $null -ne $q.string_case){throw "Prior program identity/generated assembly changed: $($entry.method)"}
        if($entry.method -in @('uncaught','throwing')){
            $class=if($entry.method -eq 'uncaught'){'dev/boom/unwind/UnwindProgram$Child'}else{'java/lang/IllegalStateException'};$owner=@($q.classes|Where-Object name -eq $class)[0]
            [BoomUnwindProbe]::Uncaught($q.compilation.dll,$owner.id);$calls=2
        }elseif($null -ne $q.exception_runtime){
            $before=[BoomUnwindProbe]::Run($p.compilation.dll,(Join-Path $folder 'fpstate.dll'),[uint32[]]@(0,1,2,4294967295));$after=[BoomUnwindProbe]::Run($q.compilation.dll,(Join-Path $folder 'fpstate.dll'),[uint32[]]@(0,1,2,4294967295))
            if(($before -join '|') -ne ($after -join '|')){throw 'Rebuilt Context32 native behavior differs'};$calls=12
        }else{
            $argumentCount=@($p.compilation.signature.arguments).Count
            [string[]]$values=@(foreach($n in @('0','1','ffffffff')){$argsForEntry=@(for($i=0;$i -lt $argumentCount;$i++){if($i -eq 0){$n}else{'0'}});$argsForEntry -join ' '})
            $type=$entry.descriptor[$entry.descriptor.Length-1]
            $before=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $folder 'fpstate.dll'),$values,$type,$true);$after=[BoomNumericProbe]::Run($q.compilation.dll,(Join-Path $folder 'fpstate.dll'),$values,$type,$true)
            if(($before -join '|') -ne ($after -join '|')){throw 'Rebuilt legacy native behavior differs'};$calls=6
        }
        $executions+=$calls;$checks.Add([ordered]@{prior_program=$file.FullName;program=(Join-Path $out 'program.json');entry=($entry.class_name+'.'+$entry.method+$entry.descriptor);profile=$q.schema;input_fingerprint=$q.input_fingerprint;assembly_sha256=$q.compilation.assembly_digest.sha256;unchanged_input_and_generated_assembly=$true;current_native_executions=$calls})
        Write-Output "Rebuilt and executed unchanged profile $($q.schema): $($entry.method)"
    }
}
if($checks.Count -ne 55 -or (Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Prior rebuild scope/compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;prior_compiler_sha256=$prior.release_sha256;compared_programs=$checks.Count;current_native_executions=$executions;input_identity_and_generated_assembly_unchanged=$true;checks=@($checks.ToArray());passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 9
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-prior-program-rebuilds.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output "Verified $($checks.Count) prior programs and $executions current native calls: $root"
exit 0
