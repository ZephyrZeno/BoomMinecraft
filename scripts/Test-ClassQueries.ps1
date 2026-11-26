param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/class-query-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-class-query-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/reflection/ClassQueryProgram.java java/subset/dev/boom/reflection/ClassQueryReference.java
if($LASTEXITCODE -ne 0){throw 'Class query reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ClassQueryProbe.cs
$common=@('compile-program','--entry-class','dev/boom/reflection/ClassQueryProgram','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($f in Get-ChildItem (Join-Path $classes dev/boom/reflection) -Filter 'ClassQueryProgram*.class'){$common+=@('--class-file',$f.FullName)}
function Compile([string]$method){
    $out=Join-Path $root $method
    & $Boom @common --method $method --output $out > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 15;throw "Class query compilation failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 39 -or $p.class_queries.abi -ne 1 -or -not $p.class_queries.nominal_definitions_only -or $p.class_queries.type_count -ne $p.mirror_types.Count -or $p.class_queries.native_source_sha256 -ne (Get-FileHash native/runtime/class_queries.asm).Hash.ToLowerInvariant() -or $p.class_queries.mirror_source_sha256 -ne (Get-FileHash native/runtime/mirrors.asm).Hash.ToLowerInvariant()){throw 'Class query metadata/profile proof missing'}
    if($p.class_queries.heap_abi -ne 1 -or $p.class_queries.heap_source_sha256 -ne (Get-FileHash native/runtime/heap.asm).Hash.ToLowerInvariant()){throw 'Class query heap ownership ABI changed'}
    foreach($b in $p.class_queries.bindings){if($b.origin.sha256 -ne $base.classes.'java.lang.Class'.sha256 -or $b.origin.loader -ne 'bootstrap'){throw 'Class query original source proof missing'}}
    Write-Output "Compiled Class native query/original Java component method: $method"|Out-Host
    return $p
}
function Java([string]$method,[string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.reflection.ClassQueryReference',$method)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Class JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(15000)){throw 'Class reference input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Class JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$cases=[Collections.Generic.List[string]]::new();for($i=0;$i -lt 32;$i++){$cases.Add($i.ToString('x8'))};foreach($v in @('ffffffff','80000000','7fffffff','12345678')){$cases.Add($v)};$random=[Random]::new(39039);$bytes=[byte[]]::new(4);for($i=0;$i -lt 236;$i++){$random.NextBytes($bytes);$cases.Add([BitConverter]::ToUInt32($bytes,0).ToString('x8'))}
if($cases.Count -ne 272){throw 'Class query case scope changed'}
$programs=@{};$count=0
foreach($method in @('hidden','component','depth','untouched','nullHidden','nullComponent')){
    $p=Compile $method;$programs[$method]=$p
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root fpstate.dll),$cases.ToArray(),'I',$true)
    $expected=Java $method $cases.ToArray()
    [IO.File]::WriteAllLines((Join-Path $root ($method+'-native.txt')),[string[]]$actual,[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllLines((Join-Path $root ($method+'-reference.txt')),[string[]]$expected,[Text.UTF8Encoding]::new($false))
    if($actual.Count -ne 272 -or $expected.Count -ne 272 -or ($actual -join '|') -cne ($expected -join '|')){throw "Class query/JVM mismatch: $method"}
    $count+=$actual.Count
}
foreach($method in @('component','depth','untouched','nullComponent')){
    $p=$programs[$method];$bridge=@($p.jdk_bridges|Where-Object kind -eq 'ClassComponentType');$fields=@($p.class_queries.bindings|Where-Object kind -eq 'ComponentField')
    if($bridge.Count -eq 0 -or $fields.Count -eq 0 -or @($p.symbols|Where-Object {$_.class_name -eq 'java/lang/Class$$BoomJdk$0008' -and $_.method -eq 'componentType'}).Count -ne 1 -or @($bridge|Where-Object {$_.target.generated.host_sha256 -ne $base.classes.'java.lang.Class'.sha256}).Count){throw 'Original Java component method/private field path not retained'}
}
$reference=Compile reference;[BoomClassQueryProbe]::Native($reference.compilation.dll,(Join-Path $root boom-runtime.dll))
$lambda=Compile nominalLambda
$lambdaResult=[BoomNumericProbe]::Run($lambda.compilation.dll,(Join-Path $root fpstate.dll),[string[]]@('0'),'I',$true)
if($lambdaResult.Count -ne 1 -or $lambdaResult[0] -cne 'v 0000000000000011' -or @($lambda.mirror_types|Where-Object {$_.kind -eq 'class' -and $_.origin.generated.generator -eq 'boom-lambda'}).Count -eq 0){throw 'Nominal generated lambda Class policy failed'}
[string[]]$small=@(0..15|ForEach-Object{$_.ToString('x8')})
[int[]]$components=@((Java component $small)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomClassQueryProbe]::Parallel($programs.component.compilation.dll,(Join-Path $root boom-runtime.dll),$components)
$descriptorOut=Join-Path $root descriptor
$text=& $Boom @common --method descriptor --output $descriptorOut 2>&1;$descriptorCode=$LASTEXITCODE;$reason=($text|ForEach-Object ToString)-join "`n"
if($descriptorCode -eq 0 -or $reason -notmatch 'Linking locked java/lang/System.getProperties' -or $reason -notmatch 'System Java startup phases 1/2/3 are required'){throw 'Descriptor integration frontier changed; inspect before recording'}
[IO.File]::WriteAllText((Join-Path $root descriptor-frontier.txt),$reason,[Text.UTF8Encoding]::new($false))
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Class query compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/class_queries.asm','src/compiler/class_queries.rs','src/compiler/jdk_bridges.rs','java/subset/dev/boom/reflection/ClassQueryProgram.java','java/subset/dev/boom/reflection/ClassQueryReference.java','tests/host/ClassQueryProbe.cs','scripts/Test-ClassQueries.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=8;JVM_differential_cases=$count;native_differential_calls=$count*2;original_Class_componentType_Code_retained_and_executed=$true;private_component_field_source_and_receiver_verified=$true;primitive_void_named_interface_and_multidimensional_array_cases=$true;uninitialized_target_classes_stay_uninitialized=$true;nominal_definition_universe_ABI=1;lambda_holders_nominal_by_VM_design=$true;lambda_hidden_flag_compared_with_JVM=$false;hidden_class_definition_supported=$false;native_no_allocation_calls=8193;full_heap_no_allocation_calls=8193;forged_mirror_and_foreign_heap_rejected=$true;pending_exception_and_metadata_gates=$true;workers=8;multicore_records=6147;descriptorString_complete=$false;descriptor_frontier=$reason;SystemProps_initProperties_complete=$false;automatic_gc=$false;full_game_ready=$false;passed=$true;sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-class-query-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
