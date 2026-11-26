param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/vm-property-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-vm-property-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
if($LASTEXITCODE -ne 0){throw 'VM property runtime build failed'}
Add-Type -Path tests/host/VmPropertyProbe.cs
$profile=[ordered]@{schema=1;java_home=(Join-Path $root '原生映像 🧱');class_path='alpha.jar;类库 β.jar';library_path=(Join-Path $root native);properties=@(@{key='boom.test';value='old'},@{key='boom.empty';value=$null},@{key='boom.test';value="汉字 🧱 é=\`r`n"},@{key='file.encoding';value='UTF-8'},@{key='boom.oracle';value="VM property =\`r`n"})}
$profilePath=Join-Path $root profile.json
function SaveProfile { [IO.File]::WriteAllText($profilePath,($profile|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false)) }
function Compile([string]$name,[switch]$Configured){
    $out=Join-Path $root $name;$arguments=@('compile-locked-program','--lock',$MetadataLock,'--jdk-base',$JdkBase,'--entry-class','jdk/internal/util/SystemProps$Raw','--method','vmProperties','--descriptor','()[Ljava/lang/String;','--output',$out,'--assemble')
    if($Configured){$arguments+=@('--vm-profile',$profilePath)}
    & $Boom @arguments > (Join-Path $root ($name+'-compile.json')) 2> (Join-Path $root ($name+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($name+'-compile.err')) -Tail 12;throw 'Original VM native entry compilation failed'}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -lt 38 -or $p.vm_properties.abi -ne 1 -or $p.vm_properties.entry_method_id -ne $p.entry_id -or $p.compilation.instructions -ne 0 -or $p.symbols.Count -ne 1 -or $p.vm_properties.origin.sha256 -ne $base.classes.'jdk.internal.util.SystemProps$Raw'.sha256 -or $p.vm_properties.native_source_sha256 -ne (Get-FileHash native/runtime/vm_properties.asm).Hash.ToLowerInvariant() -or $p.full_game_ready){throw 'Native VM entry/source proof missing'}
    if($p.vm_properties.string_storage_abi -ne 3){throw 'VM property String ABI changed'}
    foreach($binding in @(@('string_source_sha256','native/runtime/strings.asm'),@('heap_source_sha256','native/runtime/heap.asm'),@('reference_source_sha256','native/runtime/references.asm'))){if($p.vm_properties.($binding[0]) -ne (Get-FileHash $binding[1]).Hash.ToLowerInvariant()){throw 'VM property dependency source proof changed'}}
    return $p
}
function Expected($p){
    $strings=@{};foreach($literal in $p.string_literals){$chars=[char[]]@($literal.utf16|ForEach-Object{[char]$_});$strings[[int]$literal.id]=[string]::new($chars)}
    $keys=[Collections.Generic.List[string]]::new();$values=[Collections.Generic.List[string]]::new()
    foreach($row in $p.vm_properties.rows){$key=$strings[[int]$row.key_literal];if($key -cne $row.name){throw 'VM key literal/name mismatch'};$keys.Add($key);$values.Add($strings[[int]$row.value_literal])}
    return @{keys=$keys.ToArray();values=$values.ToArray()}
}
function Basic($p){$e=Expected $p;[BoomVmPropertyProbe]::Basic($p.compilation.dll,$e.keys,$e.values)}
$default=Compile default;Basic $default
$expectedHome=[IO.Path]::GetFullPath((Join-Path $root default));if($default.vm_properties.profile.java_home -ne $expectedHome){throw 'Default VM java.home is not the native image directory'}
SaveProfile;$configured=Compile configured -Configured;Basic $configured
$repeat=Compile repeat -Configured
if($repeat.input_fingerprint -ne $configured.input_fingerprint -or $repeat.compilation.assembly_digest.sha256 -ne $configured.compilation.assembly_digest.sha256){throw 'Identical frozen profiles produced different identities/ASM'}
$e=Expected $configured;$map=@{};for($i=0;$i -lt $e.keys.Count;$i++){$map[$e.keys[$i]]=$e.values[$i]}
if($map['boom.test'] -cne $profile.properties[2].value -or $map['boom.empty'] -cne '' -or $map['java.vm.name'] -cne 'BoomMinecraft Assembly VM' -or $map['java.home'] -cne $profile.java_home -or $map['java.class.path'] -cne $profile.class_path -or $map['java.library.path'] -cne $profile.library_path){throw 'Profile values, identity or last-definition-wins mismatch'}
[BoomVmPropertyProbe]::Parallel($configured.compilation.dll,(Join-Path $root boom-runtime.dll),$e.keys,$e.values)
[BoomVmPropertyProbe]::Oom($configured.compilation.dll,(Join-Path $root boom-runtime.dll),$e.keys,$e.values)
Write-Output 'Validated frozen profiles, original VM native entry, 6147 ASM worker records, hot array-only allocation and OOM recovery'
$classes=Join-Path $root classes
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/properties/VmRawReference.java
if($LASTEXITCODE -ne 0){throw 'VM reference javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('--add-opens','java.base/jdk.internal.util=ALL-UNNAMED','-Dboom.oracle=old',('-Dboom.oracle='+$profile.properties[4].value),'-Dboom.empty','-Dfile.encoding=UTF-8','-cp',$classes,'dev.boom.properties.VmRawReference','boom.oracle','boom.empty','file.encoding')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'VM reference start failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'VM property JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$reference=@($stdout.GetAwaiter().GetResult().TrimEnd("`r","`n").Split("`n")|ForEach-Object{[Text.Encoding]::BigEndianUnicode.GetString([Convert]::FromBase64String($_.Trim()))})}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
if($reference.Count -ne 3 -or $reference[0] -cne $map['boom.oracle'] -or $reference[1] -cne $map['boom.empty'] -or $reference[2] -cne $map['file.encoding']){throw 'Original JVM native property text/override mismatch'}
$profile.properties[2].value='changed';SaveProfile;$changed=Compile changed -Configured;Basic $changed
if($changed.input_fingerprint -eq $configured.input_fingerprint -or $changed.compilation.assembly_digest.sha256 -eq $configured.compilation.assembly_digest.sha256){throw 'Changed profile did not invalidate identity and ASM'}
$badProfiles=@(@{key='java.vm.name';value='other'},@{key='sun.nio.MaxDirectMemorySize';value='1'},@{key='';value='x'})
foreach($bad in $badProfiles){$profile.properties=@($bad);SaveProfile;$out=Join-Path $root ('invalid-'+[guid]::NewGuid().ToString('N'));$text=& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --vm-profile $profilePath --entry-class 'jdk/internal/util/SystemProps$Raw' --method vmProperties --descriptor '()[Ljava/lang/String;' --output $out --assemble 2>&1;if($LASTEXITCODE -eq 0 -or (Test-Path $out) -or ($text -join ' ') -notmatch 'VM-owned|Invalid VM property'){throw 'Invalid VM profile accepted or wrote outputs'}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'VM property compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/vm_properties.asm','src/compiler/vm_properties.rs','tests/host/VmPropertyProbe.cs','java/subset/dev/boom/properties/VmRawReference.java','scripts/Test-VmProperties.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_artifacts=4;executed_native_entries=3;original_private_Raw_vmProperties_native_verified=$true;original_Java_cmdProperties_executed=$false;JVM_selected_property_comparisons=3;native_VM_identity_not_copied_from_JVM=$true;frozen_profile_paths_and_last_override_win=$true;same_profile_identity_and_ASM_reproduced=$true;changed_profile_invalidates_identity_and_ASM=$true;fresh_private_terminated_String_arrays=$true;hot_allocation_calls=384;guest_allocations_per_hot_call=1;immutable_literal_roots_reused=$true;workers=8;multicore_records=6147;cold_and_warm_full_heap_OOM=$true;partial_array_OOM_reclaimed_and_recovered=$true;pending_exception_and_metadata_gates=$true;System_initPhase1_complete=$false;SystemProps_initProperties_complete=$false;automatic_gc=$false;full_game_ready=$false;passed=$true;sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-vm-property-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
