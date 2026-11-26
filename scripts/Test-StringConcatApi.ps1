param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/string-concat-api-tests/'+[guid]::NewGuid().ToString('N'));$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
[IO.File]::WriteAllText('.boom/current-string-concat-api-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/concatapi/ConcatApiProgram.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'String concat reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root > (Join-Path $root 'runtime-build.log') 2>&1
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root 'fp-build.log') 2>&1
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ConcatApiProbe.cs
$methods=@('literals','units','dynamic','chain','copyIdentity','interned','nullSuffix','nullReceiver','parallel','allocation','fullHeap','objects');$programs=@{}
foreach($method in $methods){
    $descriptor=if($method -eq 'units'){'(II)I'}elseif($method -eq 'objects'){'(I)Ljava/lang/String;'}else{'(I)I'}
    & $Boom compile-program --class-file (Join-Path $classes 'dev/boom/concatapi/ConcatApiProgram.class') --entry-class dev/boom/concatapi/ConcatApiProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root $method) --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 15;throw "String.concat compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 34 -or $p.backend -ne 'boom-string-concat-api-program-v34-masm-x64' -or $p.string_concat_api.Count -eq 0){throw 'String.concat source bindings missing'}
    foreach($b in $p.string_concat_api){if($b.abi -ne 1 -or $b.origin.sha256 -ne $base.classes.'java.lang.String'.sha256 -or $b.helper_origin.sha256 -ne $base.classes.'java.lang.StringConcatHelper'.sha256 -or $b.native_source_sha256 -ne (Get-FileHash native/runtime/string_concat_api.asm).Hash.ToLowerInvariant()){throw 'String.concat source/native proof changed'}}
    if(($method -in @('nullSuffix','nullReceiver','fullHeap')) -ne ($null -ne $p.exception_runtime)){throw 'String.concat changed Context32 boundary'}
    $programs[$method]=$p;Write-Output "Compiled original String.concat contract: $method"
}
function Java([string]$text){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Concat JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($text).Wait(15000)){throw 'Concat JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Concat JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$cases=@{};$values=[Collections.Generic.List[string]]::new();foreach($v in @(0,1,2,3,4,7,8,15,16,127,128,255,65535,2147483647,2147483648,[uint32]::MaxValue)){$values.Add(([uint32]$v).ToString('x'))}
[uint64]$seed=0x12345678
for($i=0;$i -lt 128;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
foreach($method in $methods|Where-Object {$_ -notin @('objects','literals','units')}){$cases[$method]=$values}
$cases.literals=@(foreach($i in 0..255){$i.ToString('x')});$cases.units=[Collections.Generic.List[string]]::new()
foreach($a in @(0,1,65,255,256,32767,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,0xe000,65535)){foreach($b in @(0,1,65,255,256,32767,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,0xe000,65535)){$cases.units.Add($a.ToString('x')+' '+$b.ToString('x'))}}
for($i=0;$i -lt 512;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$a=$seed -band 65535;$seed=($seed*1664525+1013904223) -band 0xffffffffL;$b=$seed -band 65535;$cases.units.Add($a.ToString('x')+' '+$b.ToString('x'))}
$numeric=@($methods|Where-Object {$_ -ne 'objects'})
$lines=@(foreach($method in $numeric){foreach($value in $cases[$method]){'dev.boom.concatapi.ConcatApiProgram '+$method+' '+$(if($method -eq 'units'){'(II)I'}else{'(I)I'})+' '+$value}})
$expected=@((Java (($lines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Concat JVM reference count mismatch'}
$index=0
foreach($method in $numeric){$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),[string[]]$cases[$method],'I',$true);foreach($value in $actual){if($value -ne $expected[$index]){throw "Concat JVM mismatch: $method at $index, native=$value, JVM=$($expected[$index])"};$index++};Write-Output "Validated String.concat JVM differential and native GC: $method"}
[BoomConcatApiProbe]::ObjectsAndFailures($programs.objects.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
[BoomConcatApiProbe]::AllocationPaths($programs.allocation.compilation.dll)
[BoomConcatApiProbe]::FullHeap($programs.fullHeap.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
$parallelLines=@(foreach($i in 0..2048){'dev.boom.concatapi.ConcatApiProgram parallel (I)I '+$i.ToString('x')})
$parallelExpected=@((Java (($parallelLines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Trim().Substring(2),16)),0)})
[BoomConcatApiProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root 'boom-runtime.dll'),[int[]]$parallelExpected)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Concat compiler changed during run'}
$sources=[ordered]@{};foreach($path in @('native/runtime/string_concat_api.asm','java/subset/dev/boom/concatapi/ConcatApiProgram.java','tests/host/ConcatApiProbe.cs','scripts/Test-StringConcatApi.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{backend='boom-string-concat-api-program-v34-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;differential_cases=$lines.Count;native_differential_executions=($lines.Count*2);workers=8;multicore_records=6147;UTF16_NUL_and_isolated_surrogates=$true;empty_suffix_preserves_identity_and_zero_allocation=$true;empty_receiver_fresh_object_shared_immutable_backing=$true;dynamic_shared_backing_retained_by_GC=$true;allocation_budget_calls=256;full_heap_source_calls=256;full_heap_OOM_catch_calls=192;full_heap_no_allocation_identity_calls=64;partial_allocation_OOM_and_recovery=$true;metadata_and_heap_binding_gates=$true;pending_error_preserved=$true;sources=$sources;automatic_gc=$false;System_properties_bootstrap_complete=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-string-concat-api-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
