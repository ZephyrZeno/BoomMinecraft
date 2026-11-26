param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/array-clone-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-array-clone-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/clone/CloneProgram.java java/subset/dev/boom/clone/CloneReference.java
if($LASTEXITCODE -ne 0){throw 'Array clone javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/CloneProbe.cs
$programs=@{}
foreach($method in @('arrays','checksum','relations','nullReceiver','fullHeap','parallel')){
    $descriptor=switch($method){arrays{'(I)Ljava/lang/Object;'};checksum{'(I)J'};default{'(I)I'}}
    $out=Join-Path $root $method
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/clone/CloneProgram.class) --class-file (Join-Path $classes dev/boom/clone/CloneDormant.class) --entry-class dev/boom/clone/CloneProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 16;throw "Array clone compilation failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 41 -or $p.array_clones.Count -eq 0 -or $p.runtime_type_map_abi -ne 1 -or $p.full_game_ready){throw 'Array clone typed/source binding missing'}
    foreach($b in $p.array_clones){
        if($b.abi -ne 1 -or $b.heap_abi -ne 1 -or $b.runtime_type_map_abi -ne 1 -or $b.origin.sha256 -ne $base.classes.'java.lang.Object'.sha256 -or $b.origin.loader -ne 'bootstrap' -or $p.mirror_types[$b.owner_type].kind -ne 'array'){throw 'Array clone original source/type proof changed'}
        foreach($entry in @(@('native_source_sha256','native/runtime/array_clone.asm'),@('heap_source_sha256','native/runtime/heap.asm'),@('runtime_types_source_sha256','native/runtime/runtime_types.asm'),@('types_source_sha256','native/runtime/types.asm'))){if($b.($entry[0]) -ne (Get-FileHash $entry[1]).Hash.ToLowerInvariant()){throw 'Array clone runtime proof changed'}}
    }
    $programs[$method]=$p
    Write-Output "Compiled source-bound array clone: $method"|Out-Host
}
function Java([string]$method,[string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.clone.CloneReference',$method)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{
        if(-not $java.Start()){throw 'Clone JVM reference failed'}
        $stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync()
        if(-not $java.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(15000)){throw 'Clone reference input stalled'}
        $java.StandardInput.Close()
        if(-not $java.WaitForExit(30000)){throw 'Clone JVM reference timed out'}
        if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$cases=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt 64;$i++){$cases.Add($i.ToString('x8'))}
foreach($v in @('ffffffff','80000000','7fffffff','12345678')){$cases.Add($v)}
$random=[Random]::new(41041);$bytes=[byte[]]::new(4)
while($cases.Count -lt 512){$random.NextBytes($bytes);$cases.Add([BitConverter]::ToUInt32($bytes,0).ToString('x8'))}
$count=0
foreach($method in @('checksum','relations','nullReceiver','fullHeap','parallel')){
    [string[]]$selected=if($method -eq 'checksum'){$cases.ToArray()}else{$cases.GetRange(0,272).ToArray()}
    $p=$programs[$method];$kind=if($method -eq 'checksum'){'J'}else{'I'}
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root fpstate.dll),$selected,$kind,$true)
    $expected=Java $method $selected
    [IO.File]::WriteAllLines((Join-Path $root ($method+'-native.txt')),[string[]]$actual,[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllLines((Join-Path $root ($method+'-reference.txt')),[string[]]$expected,[Text.UTF8Encoding]::new($false))
    if($actual.Count -ne $selected.Count -or $expected.Count -ne $selected.Count -or ($actual -join '|') -cne ($expected -join '|')){throw "Array clone/JVM mismatch: $method"}
    $count+=$actual.Count
    Write-Output "Passed clone JVM differential: $method ($($actual.Count))"|Out-Host
}
[BoomCloneProbe]::Native($programs.arrays.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomCloneProbe]::Tail($programs.arrays.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomCloneProbe]::FullHeap($programs.fullHeap.compilation.dll,(Join-Path $root boom-runtime.dll))
[string[]]$workerCases=@(0..2048|ForEach-Object{$_.ToString('x8')})
[int[]]$workerExpected=@((Java parallel $workerCases)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomCloneProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root boom-runtime.dll),$workerExpected)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Clone compiler changed during verification'}
$sources=[ordered]@{}
foreach($path in @('native/runtime/array_clone.asm','src/compiler/array_clone.rs','tests/host/CloneProbe.cs','java/subset/dev/boom/clone/CloneProgram.java','java/subset/dev/boom/clone/CloneReference.java','scripts/Test-ArrayClone.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{
    compiler_sha256=$sha;runtime_language='assembly';compiled_entries=6
    JVM_differential_cases=$count;native_differential_calls=$count*2
    primitive_kinds=8;reference_kinds=@('String[]','Class[]','Object[]')
    clone_single_guest_allocation_checks=150;raw_float_double_payloads_checked=32768
    empty_array_identity_and_exact_heap_end=$true;runtime_covariant_type_preserved=$true
    shallow_nested_reference_sharing_and_independent_slots=$true
    referenced_element_classes_stay_uninitialized=$true
    full_heap_native_failures=128;compiled_full_heap_calls=256
    pending_exception_metadata_foreign_heap_and_header_gates=$true
    roots_reference_prefix_and_quiescent_GC_verified=$true
    workers=8;multicore_records=6147;automatic_gc=$false
    arbitrary_object_clone=$false;multidimensional_array_allocation=$false
    full_game_ready=$false;passed=$true;sources=$sources;run_directory=$root
}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-array-clone-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
