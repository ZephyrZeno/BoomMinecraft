param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$JdkModules='',[string]$ExistingRun='',[string]$Runtime='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
if(-not $JdkModules){$JdkModules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json}
if(-not $ExistingRun){
$root=Join-Path (Get-Location) ('.boom/class-name-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-class-name-test.txt',$root)
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
$sources=@((Get-ChildItem java/subset/dev/boom/lookup -Filter '*.java').FullName)+@('java/reference/ClassNameReference.java')
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes @sources
if($LASTEXITCODE -ne 0){throw 'Class name fixture/reference javac failed'}
$arguments=@('compile-program','--vm-class-lookup','--entry-class','dev/boom/lookup/ClassNameProgram','--method','mirror','--descriptor','(I)Ljava/lang/Class;','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--jdk-modules',$JdkModules,'--output',(Join-Path $root program),'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes dev/boom/lookup) -Filter '*.class'){$arguments+=@('--class-file',$file.FullName)}
& $Boom @arguments > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 8;throw 'Class name compilation failed'}
[IO.File]::WriteAllText((Join-Path $root compiler-sha256.txt),$sha)
}else{$root=$ExistingRun;if(-not (Test-Path (Join-Path $root compiler-sha256.txt)) -or (Get-Content (Join-Path $root compiler-sha256.txt) -Raw).Trim() -ne $sha){throw 'Reused lookup artifacts require the exact original compiler'};$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json}
$cases=[Collections.Generic.List[string]]::new()
function Case([string]$name,[bool]$initialize=$false,[int]$loader=1){$units=if($null -eq $name){'null'}elseif($name.Length -eq 0){'-'}else{(@($name.ToCharArray()|ForEach-Object{([int]$_).ToString('x4')})) -join ','};$cases.Add("$loader $([int]$initialize) $units")}
Case 'dev.boom.lookup.Aa' $true
foreach($name in @('dev.boom.lookup.Aa','dev.boom.lookup.BB','dev.boom.lookup.Child','dev.boom.lookup.Passive','dev.boom.lookup.ArrayTarget','dev.boom.lookup.Parent','dev.boom.lookup.BadInit','java.lang.String','java.lang.Class','[I','[[I','[Ldev.boom.lookup.ArrayTarget;')){Case $name}
Case 'dev.boom.lookup.Aa' $false 0
Case 'java.lang.String' $false 0
Case '[Ldev.boom.lookup.ArrayTarget;' $true
Case '[[I' $true
Case 'dev.boom.lookup.BB' $true
Case 'dev.boom.lookup.Child' $true
Case 'dev.boom.lookup.Passive'
Case 'dev.boom.lookup.Passive' $true
Case 'dev.boom.lookup.ArrayTarget' $true
Case 'dev.boom.lookup.BadInit'
Case 'dev.boom.lookup.BadInit' $true
Case 'dev.boom.lookup.BadInit' $true
Case 'dev.boom.lookup.BadInit'
foreach($name in @('','dev.boom.lookup.Missing','[Ldev.boom.lookup.Missing;','[V','void','int','java/lang/String','[','[[','[Q','[Ibad','[L;')){Case $name}
$cases.Add('1 0 null')
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'ClassNameReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Class name JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();foreach($line in $cases){$jvm.StandardInput.WriteLine($line)};$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(30000)){$jvm.Kill($true);throw 'Class name JVM timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
$ids=[Collections.Generic.List[uint32]]::new();$names=[Collections.Generic.List[string]]::new();foreach($layout in $p.object_layouts){$ids.Add([uint32]$layout.class_id);$names.Add($layout.class_name.Replace('/','.'))}
function MirrorName([int]$id){$t=$p.mirror_types[$id];if($t.kind -eq 'class'){return $t.key.name.Replace('/','.')};if($t.kind -eq 'primitive'){return $t.value.ToLowerInvariant()};$component=$p.mirror_types[$t.component];$name=MirrorName $t.component;if($component.kind -eq 'class'){return "[L$name;"};if($component.kind -eq 'array'){return "[$name"};$codes=@{boolean='Z';byte='B';char='C';short='S';int='I';long='J';float='F';double='D'};return "[$($codes[$name])"}
$mirrorNames=@(for($i=0;$i -lt $p.mirror_types.Count;$i++){MirrorName $i})
$loaders=@($p.class_loaders.type_loader_ids|ForEach-Object{$p.class_loaders.keys[$_]})
$state=@($p.classes|Where-Object name -eq dev/boom/lookup/Counters)[0];$mask=@($state.fields|Where-Object name -eq mask)[0];$aa=@($state.fields|Where-Object name -eq aaCount)[0]
$cause=@($p.exception_runtime.factories|Where-Object kind -eq 19)[0].fields|Where-Object name -eq cause
$message=@($p.exception_runtime.factories|Where-Object kind -eq 19)[0].fields|Where-Object name -eq detailMessage
$appKey=[Array]::IndexOf($p.class_loaders.keys,'explicit-application');$layout=$p.class_loaders.loader_vm_layout
& D:/Dev/Python312/python.exe scripts/verify-class-for-name.py (Join-Path $root program/program.json) $JdkBase $JdkModules > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent class name source/identity proof failed'}
Add-Type -Path tests/host/ClassNameProbe.cs
$actual=[BoomClassNameProbe]::Run($p.compilation.dll,$cases.ToArray(),$ids.ToArray(),$names.ToArray(),[string[]]$mirrorNames,[string[]]$loaders,[uint32]$state.id,[uint32]$mask.index,[uint32]$aa.index,[uint32]$cause.offset,[uint32]$message.offset,[uint32]$appKey,[uint32]$p.class_loaders.loader_type,[uint64]$layout.payload_bytes,[uint32]$layout.reference_prefix_fields)
if($Runtime){$packaged=[BoomClassNameProbe]::Run($p.compilation.dll,$cases.ToArray(),$ids.ToArray(),$names.ToArray(),[string[]]$mirrorNames,[string[]]$loaders,[uint32]$state.id,[uint32]$mask.index,[uint32]$aa.index,[uint32]$cause.offset,[uint32]$message.offset,[uint32]$appKey,[uint32]$p.class_loaders.loader_type,[uint64]$layout.payload_bytes,[uint32]$layout.reference_prefix_fields,(Resolve-Path $Runtime).Path);if(($packaged -join '|') -cne ($actual -join '|')){throw 'Full runtime class name results differ'}}
$expected|Set-Content (Join-Path $root expected.txt);$actual|Set-Content (Join-Path $root actual.txt);$cases|Set-Content (Join-Path $root cases.txt)
if($actual.Count -ne $expected.Count){throw 'Class name/JVM case count mismatch'}
for($i=0;$i -lt $expected.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Class name/JVM mismatch at $i`: $($actual[$i]) vs $($expected[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Class name compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;full_runtime_tested=[bool]$Runtime;full_runtime_sha256=$(if($Runtime){(Get-FileHash $Runtime).Hash.ToLowerInvariant()}else{''});JVM_cases=$cases.Count;name_catalog_rows=$p.class_for_name.catalog.Count;lookup_hash_collisions_checked=$true;canonical_mirrors=$true;class_initialization_order_and_default_interfaces_checked=$true;array_lookup_does_not_initialize_component=$true;failed_initialization_cause_chain_checked=$true;parallel_workers=8;parallel_cold_lookups=1024;target_initializer_executes_exactly_once=$true;pending_context_preserved=$true;foreign_heap_wrong_type_bad_metadata_rejected=$true;hot_lookup_zero_allocation_at_full_heap=$true;OOM_and_explicit_reclamation_checked=$true;VM_metadata_fixture=$true;original_Java_Class_forName_executed=$false;original_Java_ClassLoader_constructor_executed=$false;dynamic_class_definition=$false;dynamic_array_metadata=$false;security_manager_supported=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-class-name-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
