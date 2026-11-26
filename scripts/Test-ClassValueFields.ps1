param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v81/boom-runtime.dll',[string]$ExistingRun='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=if($ExistingRun){[IO.Path]::GetFullPath($ExistingRun)}else{Join-Path (Get-Location) ('.boom/class-value-field-tests/'+[guid]::NewGuid().ToString('N'))};[IO.Directory]::CreateDirectory($root)|Out-Null
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$modules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json
if(-not $ExistingRun){
 & $Boom compile-locked-program --lock .boom/locks/server.json --jdk-base $base --jdk-modules $modules --entry-class java/lang/ClassValue --method getCacheCarefully --descriptor '(Ljava/lang/Class;)[Ljava/lang/ClassValue$Entry;' --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
 if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 8;throw 'ClassValue field AOT compilation failed'}
}
& D:/Dev/Python312/python.exe scripts/verify-class-value-fields.py "$root/program/program.json" $base > "$root/source-contract.json"
if($LASTEXITCODE -ne 0){throw 'ClassValue field source contract failed'}
& D:/Dev/Java/jdk-21/bin/javac.exe -source 21 -target 21 --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -g -proc:none -d "$root/classes" java/reference/ClassValueFieldReference.java
if($LASTEXITCODE -ne 0){throw 'ClassValue field oracle javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m',"-XX:ErrorFile=$root/hs_err_pid%p.log",'--add-opens=java.base/java.lang=ALL-UNNAMED','--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',"$root/classes",'ClassValueFieldReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'ClassValue field oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'ClassValue field oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
$names=@(foreach($id in $p.mirror_name_literals){$literal=@($p.string_literals|Where-Object id -eq $id)[0];-join @($literal.utf16|ForEach-Object{[char]$_})})
$ids=@(foreach($name in @('java.lang.Object','java.lang.String','int','byte','[Ljava.lang.Object;')){$id=[Array]::IndexOf([string[]]$names,$name);if($id -lt 0){throw "Missing ClassValue test type: $name"};[uint32]$id})
$mapLayout=@($p.object_layouts|Where-Object class_name -eq 'java/lang/ClassValue$ClassValueMap')[0];$cache=@($mapLayout.layout.fields|Where-Object {$_.name -eq 'cacheArray' -and $_.declaring_class -eq 'java/lang/ClassValue$ClassValueMap'})[0];$npe=@($p.object_layouts|Where-Object class_name -eq java/lang/NullPointerException)[0].class_id
Add-Type -Path tests/host/ClassValueFieldProbe.cs
$actual=[BoomClassValueFieldProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),[uint32[]]$ids,[uint32]$mapLayout.class_id,[uint64]$mapLayout.layout.payload_bytes,[uint32]$mapLayout.layout.reference_prefix_fields,[uint32]$cache.offset,[uint32]$npe,[uint32]$p.entry_id)
if($actual.Count -ne $expected.Count){throw 'ClassValue field oracle row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "ClassValue field differs at $i : JVM=$($expected[$i]); ASM=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'ClassValue field compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=6;workers=8;parallel_writes=8192;parallel_Java_reads=8192;warm_guest_allocations=0;original_getCacheCarefully_and_getCache_Java_bodies_executed=$true;original_ClassValue_initializer_executed=$true;original_ClassValueMap_constructor_executed=$false;original_initializeMap_Java_store_executed=$false;VM_fixture_map_objects_used=$true;per_Class_reference_cells_and_precise_static_roots_checked=$true;foreign_heap_wrong_type_and_pending_context_checked=$true;full_ClassValue_support=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-class-value-field-test.txt',$root);Write-Output $json
exit 0
