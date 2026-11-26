param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/multi-array-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-multi-array-test.txt',$root,[Text.UTF8Encoding]::new($false))
$generated=Join-Path $root generated;& D:\Dev\Python312\python.exe scripts/make-array-fixtures.py $generated
if($LASTEXITCODE -ne 0){throw 'Array fixture generation failed'}
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$java=$inputs.java.executable;$javac=Join-Path (Split-Path $java) javac.exe
& $javac --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/arrays/MultiArrayProgram.java java/subset/dev/boom/arrays/MultiArrayReference.java (Join-Path $generated DeepArray.java)
if($LASTEXITCODE -ne 0){throw 'Multiarray javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs;Add-Type -Path tests/host/CloneProbe.cs;Add-Type -Path tests/host/MultiArrayProbe.cs
$common=@('compile-program','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($f in Get-ChildItem (Join-Path $classes dev/boom/arrays) -Filter *.class){$common+=@('--class-file',$f.FullName)}
$programs=@{}
foreach($method in @('factory','primitives','jagged','references','partial','negative','nullAndBounds','fullHeap','parallel','deep','empty','negativeDeep')){
    $deep=$method -in @('deep','empty','negativeDeep');$entry=if($deep){'dev/boom/arrays/DeepArray'}else{'dev/boom/arrays/MultiArrayProgram'};$actualMethod=if($method -eq 'negativeDeep'){'negative'}else{$method}
    $desc=switch($method){primitives{'(II)J'};factory{'(I)Ljava/lang/Object;'};deep{'(I)Ljava/lang/Object;'};default{'(I)I'}}
    $out=Join-Path $root $method;& $Boom @common --entry-class $entry --method $actualMethod --descriptor $desc --output $out > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 14;throw "Multiarray compile failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 44 -or -not $p.typed_arrays -or $p.typed_arrays.abi -ne 1 -or $p.typed_arrays.automatic_gc -or $p.full_game_ready){throw 'Typed array plan missing'}
    foreach($pair in @(@('native_source_sha256','native/runtime/typed_arrays.asm'),@('heap_source_sha256','native/runtime/heap.asm'),@('runtime_types_source_sha256','native/runtime/runtime_types.asm'),@('types_source_sha256','native/runtime/types.asm'))){if($p.typed_arrays.($pair[0]) -ne (Get-FileHash $pair[1]).Hash.ToLowerInvariant()){throw 'Typed array dependency proof changed'}}
    foreach($site in $p.typed_arrays.sites){if($site.dimensions -lt 1 -or $site.dimensions -gt 255 -or $p.mirror_types[$site.type_id].kind -ne 'array' -or @($p.sources|Where-Object {$_.origin.sha256 -eq $site.caller.sha256 -and $_.origin.loader -eq $site.caller.loader}).Count -ne 1){throw 'Array allocation site source/rank missing'}}
    $programs[$method]=$p;Write-Output "Compiled typed array: $method"|Out-Host
}
function Java([string]$method,[string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.arrays.MultiArrayReference',$method)){$info.ArgumentList.Add($arg)};foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $p=[Diagnostics.Process]::new();$p.StartInfo=$info
    try{if(-not $p.Start()){throw 'Multiarray JVM reference failed'};$stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync();if(-not $p.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(15000)){throw 'Multiarray JVM input stalled'};$p.StandardInput.Close();if(-not $p.WaitForExit(30000)){throw 'Multiarray JVM timed out'};if($p.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})}finally{if(-not $p.HasExited){$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
}
$cases=[Collections.Generic.List[string]]::new();for($i=0;$i -lt 64;$i++){$cases.Add($i.ToString('x8'))};foreach($v in @('ffffffff','80000000','7fffffff','7fc12345','7f812345','0000d800')){$cases.Add($v)}
$random=[Random]::new(44044);$bytes=[byte[]]::new(4);while($cases.Count -lt 272){$random.NextBytes($bytes);$cases.Add([BitConverter]::ToUInt32($bytes,0).ToString('x8'))}
$count=0
foreach($method in @('primitives','jagged','references','partial','negative','nullAndBounds','fullHeap','parallel')){
    [string[]]$selected=if($method -eq 'primitives'){@(foreach($v in $cases){foreach($k in 0..7){$v+' '+$k.ToString('x8')}})}else{$cases.ToArray()}
    $kind=if($method -eq 'primitives'){'J'}else{'I'};$p=$programs[$method]
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root fpstate.dll),$selected,$kind,$true);$expected=Java $method $selected
    [IO.File]::WriteAllLines((Join-Path $root ($method+'-native.txt')),[string[]]$actual);[IO.File]::WriteAllLines((Join-Path $root ($method+'-reference.txt')),[string[]]$expected)
    if($actual.Count -ne $selected.Count -or $expected.Count -ne $selected.Count -or ($actual -join '|') -cne ($expected -join '|')){throw "Multiarray/JVM mismatch: $method"};$count+=$actual.Count
    Write-Output "Passed multiarray differential: $method ($($actual.Count))"|Out-Host
}
foreach($method in @('empty','negativeDeep')){$expected=if($method -eq 'empty'){'v 0000000000000000'}else{'v 0000000000000053'};$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root fpstate.dll),$cases.ToArray(),'I',$true);if($actual.Count -ne 272 -or @($actual|Where-Object {$_ -cne $expected}).Count){throw 'Deep zero/negative dimension semantics failed'}}
$descriptors=@('[[Z','[[B','[[C','[[S','[[I','[[J','[[F','[[D','[[[Ljava/lang/String;','[[[Ljava/lang/Class;','[[Ldev/boom/arrays/Dormant;','[[[Ljava/lang/Object;')
[uint32[]]$ids=@(foreach($d in $descriptors){$sites=@($programs.factory.typed_arrays.sites|Where-Object descriptor -eq $d);if($sites.Count -ne 1){throw 'Factory array descriptor site missing'};$sites[0].type_id})
[BoomMultiArrayProbe]::Native($programs.factory.compilation.dll,(Join-Path $root boom-runtime.dll),$ids)
$deepSite=@($programs.deep.typed_arrays.sites|Where-Object dimensions -eq 255);if($deepSite.Count -ne 1){throw 'Rank 255 allocation site missing'}
[BoomMultiArrayProbe]::Deep($programs.deep.compilation.dll,$deepSite[0].type_id)
[BoomMultiArrayProbe]::FullHeap($programs.fullHeap.compilation.dll,(Join-Path $root boom-runtime.dll))
[string[]]$workerCases=@(0..2048|ForEach-Object{$_.ToString('x8')});[int[]]$workerExpected=@((Java parallel $workerCases)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomCloneProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root boom-runtime.dll),$workerExpected)
$rejected=[Collections.Generic.List[object]]::new()
foreach($bad in Get-Content (Join-Path $generated bad-arrays.json) -Raw|ConvertFrom-Json){
    $dest=Join-Path $classes ($bad.name+'.class');Copy-Item $bad.path $dest -Force;$out=Join-Path $root ('rejected-'+[IO.Path]::GetFileNameWithoutExtension($bad.path))
    $reason=(& $Boom compile-program --class-file $bad.path --entry-class $bad.name --method run --descriptor '()Ljava/lang/Object;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or $reason -notmatch 'dimensions exceed descriptor rank|JVM limit' -or (Test-Path (Join-Path $out program.json))){throw 'Invalid multianewarray accepted'}
    $jvm=(& $java -Xverify:all -cp $classes dev.boom.arrays.MultiArrayReference bad ($bad.name.Replace('/','.')) 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or $jvm -notmatch 'VerifyError|ClassFormatError'){throw 'JVM did not reject invalid array bytecode'}
    [IO.File]::WriteAllText(($out+'-aot.txt'),$reason);[IO.File]::WriteAllText(($out+'-jvm.txt'),$jvm)
    $rejected.Add([ordered]@{name=$bad.name;source_sha256=(Get-FileHash $bad.path).Hash.ToLowerInvariant();AOT_rejected=$true;JVM_rejected=$true})
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Array compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/typed_arrays.asm','src/compiler/typed_arrays.rs','java/subset/dev/boom/arrays/MultiArrayProgram.java','java/subset/dev/boom/arrays/MultiArrayReference.java','tests/host/MultiArrayProbe.cs','tests/host/CloneProbe.cs','scripts/Test-MultiArrays.ps1','scripts/make-array-fixtures.py')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=12;JVM_differential_cases=$count;native_differential_calls=$count*2;deep_zero_negative_native_calls=1088;primitive_kinds=8;maximum_rank=255;deep_allocated_arrays=255;partial_dimensions_and_zero_cutoff=$true;negative_later_dimension_checked_with_zero_outer=$true;covariant_actual_types_and_shallow_clone=$true;checked_arraycopy_prefix_preserved=$true;component_class_stays_uninitialized=$true;negative_metadata_and_pending_context_gates=$true;partial_OOM_allocated_nodes=2;partial_OOM_reclaimed_and_recovered=$true;full_heap_source_calls=256;workers=8;multicore_records=6147;independent_root_graph_and_static_state_GC_checks=$true;rejected_bytecode=$rejected.ToArray();automatic_gc=$false;full_game_ready=$false;passed=$true;sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-multi-array-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
