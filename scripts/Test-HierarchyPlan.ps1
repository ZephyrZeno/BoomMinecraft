param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$root=Join-Path $projectRoot ('.boom\hierarchy-plan-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\hierarchy\Model.java')
if($LASTEXITCODE -ne 0){throw 'Hierarchy fixture javac failed.'}
$requests=@('Derived','DefaultI','DefaultJ','OverrideJ','AbstractK','Plain')|ForEach-Object{[ordered]@{owner='dev/boom/hierarchy/I';method='f';descriptor='(I)I';receiver="dev/boom/hierarchy/$_";interface=$true}}
$requestPath=Join-Path $root 'requests.json'
[IO.File]::WriteAllText($requestPath,($requests|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
$arguments=@('plan-hierarchy','--lock',$MetadataLock,'--jdk-base',$JdkBase,'--requests',$requestPath,'--output',(Join-Path $root 'plan.json'))
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\hierarchy') -Filter '*.class' -File){$arguments+=@('--class-file',$file.FullName)}
foreach($name in @('Base','Derived','DefaultI','DefaultJ','OverrideJ','AbstractK','I','J','K','Unused')){$arguments+=@('--class',"dev/boom/hierarchy/$name")}
& $boomPath @arguments
if($LASTEXITCODE -ne 0){throw 'Hierarchy plan failed.'}
$plan=Get-Content -LiteralPath (Join-Path $root 'plan.json') -Raw|ConvertFrom-Json
function TypeName([int]$id){return $plan.types[$id].key.name}
function TypeId([string]$name){for($i=0;$i -lt $plan.types.Count;$i++){if($plan.types[$i].key.name -eq "dev/boom/hierarchy/$name"){return $i}};throw "Missing type $name"}
$expectedOwners=@{Derived='Base';DefaultI='I';DefaultJ='J';OverrideJ='OverrideJ'}
$jvmTraces=[ordered]@{}
foreach($mode in @('Derived','DefaultI','DefaultJ')){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.hierarchy.Model',$mode)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
    try{
        if(-not $oracle.Start()){throw 'Hierarchy JVM reference failed.'}
        $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
        if(-not $oracle.WaitForExit(15000)){throw 'Hierarchy reference timed out.'}
        if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        $lines=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
        foreach($call in $plan.calls|Where-Object selection.kind -eq 'method'){
            $name=$call.request.receiver.Split('/')[-1];$owner=TypeName $call.selection.member.owner
            if($owner -ne "dev/boom/hierarchy/$($expectedOwners[$name])" -or "$name $($owner.Replace('/','.')) false" -notin $lines){throw "JVM method owner mismatch: $name"}
        }
        if('AbstractK dev.boom.hierarchy.K true' -notin $lines){throw 'JVM reabstraction mismatch.'}
        $trace=@($lines|Where-Object{$_ -like 'TRACE *'})[0];$jvmTraces[$mode]=[int]$trace.Substring(6)
    }finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
}
if($jvmTraces['Derived'] -ne 3124 -or $jvmTraces['DefaultI'] -ne 15 -or $jvmTraces['DefaultJ'] -ne 126){throw 'Unexpected JVM initialization oracle.'}
foreach($name in @('Derived','DefaultI','DefaultJ')){
    $id=TypeId $name;$state=@($plan.roots|Where-Object class -eq $id)[0]
    $deps=@($state.initialization_dependencies|ForEach-Object{TypeName $_})
    $expected=if($name -eq 'Derived'){@('dev/boom/hierarchy/Base','dev/boom/hierarchy/I','dev/boom/hierarchy/J')}elseif($name -eq 'DefaultI'){@('java/lang/Object','dev/boom/hierarchy/I')}else{@('java/lang/Object','dev/boom/hierarchy/I','dev/boom/hierarchy/J')}
    if(($deps -join ',') -ne ($expected -join ',')){throw "Initialization dependency order mismatch: $name"}
}
$baseId=TypeId 'Base';$childId=TypeId 'Derived'
$base=@($plan.roots|Where-Object class -eq $baseId)[0].layout
$child=@($plan.roots|Where-Object class -eq $childId)[0].layout
if($child.reference_prefix -ne 2 -or $child.payload_bytes -ne 32){throw 'Inherited field reference prefix mismatch.'}
if(@($base.fields|Where-Object{$_.member.name -eq 'value'})[0].offset -ne 8 -or @($child.fields|Where-Object{$_.member.name -eq 'value' -and $_.member.owner -eq $baseId})[0].offset -ne 16){throw 'Inherited scalar offset did not account for subclass references.'}
if(@($plan.calls|Where-Object{$_.request.receiver.EndsWith('/AbstractK')})[0].selection.kind -ne 'abstract_method' -or @($plan.calls|Where-Object{$_.request.receiver.EndsWith('/Plain')})[0].selection.kind -ne 'incompatible_class_change'){throw 'Wrong abstract/incompatible selection.'}
if($plan.execution_wired -or $plan.full_game_ready){throw 'Metadata plan misreported as game execution.'}
$report=[ordered]@{passed=$true;source_verified_types=$plan.types.Count;method_selection_cases=$plan.calls.Count;jvm_initialization_traces=$jvmTraces;inherited_reference_layout=$true;metadata_only=$true;execution_wired=$false;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
