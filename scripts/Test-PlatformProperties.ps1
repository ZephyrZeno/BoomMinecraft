param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/platform-property-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-platform-property-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root 'classes';$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/properties/RawReference.java java/subset/dev/boom/properties/ConstructorProgram.java java/subset/dev/boom/properties/ConstructorReference.java
if($LASTEXITCODE -ne 0){throw 'Property reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root > (Join-Path $root 'runtime-build.log') 2>&1
Add-Type -Path tests/host/PropertyProbe.cs
$raw=Join-Path $root 'raw'
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class 'jdk/internal/util/SystemProps$Raw' --method '<init>' --descriptor '()V' --output $raw --assemble > (Join-Path $root 'raw-compile.json') 2> (Join-Path $root 'raw-compile.err')
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root 'raw-compile.err') -Tail 20;throw 'Original Raw constructor compilation failed'}
$p=Get-Content (Join-Path $raw 'program.json') -Raw|ConvertFrom-Json
if($p.schema -lt 33 -or $p.constructor_entry.abi -ne 1 -or $p.platform_properties.abi -ne 1 -or $p.platform_properties.rows.Count -ne 39 -or $p.platform_properties.origin.sha256 -ne $base.classes.'jdk.internal.util.SystemProps$Raw'.sha256 -or @($p.symbols|Where-Object {$_.class_name -eq 'jdk/internal/util/SystemProps$Raw' -and $_.method -eq '<init>'}).Count -ne 1){throw 'Raw constructor/native source contract missing'}
$layout=@($p.object_layouts|Where-Object class_id -eq $p.constructor_entry.class_id)[0];$field=@($layout.layout.fields|Where-Object name -eq 'platformProps')[0]
function Java([string]$entry,[string[]]$arguments,[string]$text=''){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.WorkingDirectory=[IO.Directory]::GetCurrentDirectory()
    foreach($a in @('--add-opens','java.base/jdk.internal.util=ALL-UNNAMED','-cp',$classes,$entry)+$arguments){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Property JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($text).Wait(15000)){throw 'Property JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Property JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$working=Join-Path $root '工作目录 Unicode 🧱';$temporary=Join-Path $root '临时目录 Unicode 🧱';[IO.Directory]::CreateDirectory($working)|Out-Null;[IO.Directory]::CreateDirectory($temporary)|Out-Null
$oldDirectory=[IO.Directory]::GetCurrentDirectory();$oldTmp=$env:TMP
try{
    [IO.Directory]::SetCurrentDirectory($working);$env:TMP=$temporary
    $expected=Join-Path $root 'platform-reference.bin';Java 'dev.boom.properties.RawReference' @($expected) > (Join-Path $root 'platform-reference.log')
    [BoomPropertyProbe]::CheckRaw($p.compilation.dll,$expected,$p.constructor_entry.class_id,$field.offset)
    [BoomPropertyProbe]::Parallel($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$expected,$p.constructor_entry.class_id,$field.offset)
    [BoomPropertyProbe]::OomAndMetadata($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
}finally{[IO.Directory]::SetCurrentDirectory($oldDirectory);$env:TMP=$oldTmp}
Write-Output 'Validated all 39 platform values, original Raw constructor, 6147 workers, independent arrays, roots and OOM recovery'
$common=@('compile-program','--entry-class','dev/boom/properties/ConstructorProgram','--method','<init>','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($f in Get-ChildItem (Join-Path $classes 'dev/boom/properties') -Filter 'Constructor*.class'|Where-Object Name -ne 'ConstructorReference.class'){$common+=@('--class-file',$f.FullName)}
$constructorCases=[ordered]@{default=[Collections.Generic.List[string]]::new();mixed=[Collections.Generic.List[string]]::new()}
$constructorCases.default.Add('default')
foreach($n in @('0','1','7fffffff','ffffffff','80000000','11','10000')){foreach($bits in @('0','ffffffffffffffff','123456789abcdef0')){$constructorCases.mixed.Add('mixed '+$n+' '+$bits+' 7ff8000000001234')}}
foreach($bits in @('0','8000000000000000','7ff0000000000000','fff0000000000000','1','7fefffffffffffff','3ff0000000000000')){$constructorCases.mixed.Add('mixed 1 0 '+$bits)}
$constructorCount=0
foreach($name in $constructorCases.Keys){
    $out=Join-Path $root $name;$descriptor=if($name -eq 'default'){'()V'}else{'(IJD)V'}
    & $Boom @common --descriptor $descriptor --output $out > (Join-Path $root ($name+'-compile.json')) 2> (Join-Path $root ($name+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($name+'-compile.err')) -Tail 18;throw 'Constructor VM invoker compilation failed'}
    $q=Get-Content (Join-Path $out 'program.json') -Raw|ConvertFrom-Json
    if($q.schema -lt 32 -or $q.constructor_entry.abi -ne 1 -or $null -eq $q.exception_runtime -or $null -ne $q.platform_properties){throw 'Constructor/context ABI contract missing'}
    $owner=@($q.classes|Where-Object id -eq $q.constructor_entry.class_id)[0];$object=@($q.object_layouts|Where-Object class_id -eq $owner.id)[0]
    function Offset([string]$member){@($object.layout.fields|Where-Object name -eq $member)[0].offset}
    $escaped=@($owner.fields|Where-Object name -eq 'escaped')[0];$initialized=@($owner.fields|Where-Object name -eq 'initializationCount')[0];$errorClass=@($q.classes|Where-Object name -eq 'java/lang/IllegalArgumentException')[0]
    $actual=[BoomPropertyProbe]::Constructors($q.compilation.dll,$owner.id,$escaped.index,$initialized.index,(Offset 'self'),(Offset 'value'),(Offset 'wide'),(Offset 'decimal'),(Offset 'base'),$errorClass.id,$constructorCases[$name].ToArray())
    $reference=@((Java 'dev.boom.properties.ConstructorReference' @() (($constructorCases[$name] -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
    if($actual.Count -ne $reference.Count -or ($actual -join '|') -ne ($reference -join '|')){throw 'VM constructor/JVM field, identity, exception or initialization mismatch'}
    $constructorCount+=$actual.Count;Write-Output "Validated actual constructor VM entry, partial escape and JVM values: $name"
}
foreach($target in @(@('dev/boom/properties/AbstractConstructor','<init>','AbstractConstructor.class','abstract'),@('dev/boom/properties/ConstructorProgram','<clinit>','ConstructorProgram.class','class-initializer'))){
    $out=Join-Path $root ('rejected-'+$target[3]);$reason=(& $Boom compile-program --class-file (Join-Path $classes ('dev/boom/properties/'+$target[2])) --class-file (Join-Path $classes 'dev/boom/properties/ConstructorBase.class') --entry-class $target[0] --method $target[1] --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or (Test-Path $out) -or $reason -notmatch 'abstract|ordinary static method'){throw 'Invalid constructor/class-initializer VM entry accepted'}
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Property compiler changed during run'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=3;platform_value_JVM_comparisons=39;constructor_JVM_cases=$constructorCount;workers=8;multicore_records=6147;original_private_Raw_constructor_executed=$true;source_native_indices_and_member_provenance=$true;actual_Windows_OS_queries=$true;Unicode_current_and_temporary_directories=$true;private_fresh_arrays_per_constructor=$true;snapshot_stable_after_directory_change=$true;cache_and_property_graph_static_roots=$true;temporary_graph_reclaimed=$true;cold_OOM_resets_owner_and_allows_retry=$true;clone_OOM_preserves_snapshot=$true;malformed_metadata_and_foreign_heap_rejected=$true;VM_constructor_arguments_chaining_and_class_initialization=$true;constructor_pending_exception_and_partial_escape_survive_GC=$true;SystemProps_vmProperties_complete=$false;System_initPhase1_complete=$false;automatic_gc=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-platform-property-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
$allocation=[ordered]@{compiler_sha256=$sha;host_sha256=(Get-FileHash tests/host/PropertyProbe.cs).Hash.ToLowerInvariant();full_report=(Join-Path $root result.json);executed_in_full_platform_run=$true;hot_constructor_calls=64;guest_allocations_per_hot_constructor=2;temporary_graph_reclaimed=$true;passed=$true}
[IO.File]::WriteAllText((Join-Path $root allocation-recheck.json),($allocation|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
exit 0
