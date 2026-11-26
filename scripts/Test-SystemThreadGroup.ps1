param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/system-thread-group-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json;$classes=Join-Path $root classes
foreach($file in $inputs.java.runtime_files){if((Get-FileHash $file.path).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Group JVM oracle differs from lock'}}
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -proc:none -encoding UTF-8 -d $classes java/reference/SystemThreadGroupReference.java
if($LASTEXITCODE -ne 0){throw 'Group oracle javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('--add-opens','java.base/java.lang=ALL-UNNAMED','-Xmx128m','-cp',$classes,'SystemThreadGroupReference',(Join-Path $root fields.json))){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Group JVM oracle failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Group oracle timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
$out=Join-Path $root constructor
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/ThreadGroup --method '<init>' --descriptor '()V' --output $out --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 15;throw 'Original system ThreadGroup compilation failed'}
$p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
if($p.full_game_ready -or $p.sources.Count -ne 1 -or $p.sources[0].origin.loader -ne 'bootstrap' -or $p.sources[0].origin.generated -or $p.sources[0].origin.sha256 -ne $base.classes.'java.lang.ThreadGroup'.sha256 -or $p.symbols.Count -ne 2 -or @($p.symbols|Where-Object {$_.class_name -ne 'java/lang/ThreadGroup' -or $_.method -notin @('<init>','<clinit>')}).Count){throw 'Original group source/closure changed'}
$fields=Get-Content (Join-Path $root fields.json) -Raw|ConvertFrom-Json
if($null -ne $fields.parent -or $null -ne $fields.groups -or $null -ne $fields.weaks -or $fields.name -ne 'system' -or $fields.maxPriority -ne 10 -or $fields.ngroups -ne 0 -or $fields.nweaks -ne 0 -or $fields.daemon){throw 'Original group JVM values changed'}
$layout=@($p.object_layouts|Where-Object class_name -eq 'java/lang/ThreadGroup')[0].layout
[int[]]$offsets=@(foreach($field in @('parent','name','groups','weaks','maxPriority','ngroups','nweaks','daemon')){[int]@($layout.fields|Where-Object name -eq $field)[0].offset})
if($layout.abi -ne 2 -or $layout.reference_prefix_fields -ne 4){throw 'Original group compact layout changed'}
Add-Type -Path tests/host/SystemThreadGroupProbe.cs
[BoomSystemThreadGroupProbe]::Run($p.compilation.dll,(Join-Path $root boom-runtime.dll),$offsets,$fields.name)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Group compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('scripts/Test-SystemThreadGroup.ps1','tests/host/SystemThreadGroupProbe.cs','java/reference/SystemThreadGroupReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=1;original_ThreadGroup_constructor_and_initializer_executed=$true;source_classes=1;source_methods=2;JVM_fields_compared=8;workers=8;cold_constructor_records=6147;constructor_results_distinct=$true;literal_name_identity_preserved=$true;warm_one_allocation_calls=128;full_heap_OOM_calls=64;GC_root_graph_checked=$true;OOM_recovery=$true;original_Thread_entries_executed=0;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash (Join-Path $root fields.json)).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-system-thread-group-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
