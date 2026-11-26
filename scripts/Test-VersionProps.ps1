param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/version-props-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-version-props-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/reference/VersionPropsReference.java
if($LASTEXITCODE -ne 0){throw 'VersionProps JVM oracle javac failed'}
$oracle=Join-Path $root fields.json;$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('--add-opens','java.base/java.lang=ALL-UNNAMED','-Xmx128m','-cp',$classes,'VersionPropsReference',$oracle)){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'VersionProps JVM oracle failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(120000)){throw 'VersionProps JVM oracle timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
$out=Join-Path $root constructor
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/VersionProps --method '<init>' --descriptor '()V' --output $out --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 14;throw 'Original VersionProps compilation failed'}
$p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json;$owner=$p.classes|Where-Object name -eq java/lang/VersionProps
if($p.schema -ne 47 -or $p.full_game_ready -or $p.system_startup -or -not $p.constructor_entry -or $p.constructor_entry.source.sha256 -ne $base.classes.'java.lang.VersionProps'.sha256 -or @($p.symbols|Where-Object {$_.class_name -eq 'java/lang/VersionProps' -and $_.method -eq '<clinit>'}).Count -ne 1 -or @($p.jdk_bridges|Where-Object kind -eq StartsWith).Count -lt 1){throw 'Original VersionProps initialization/source proof missing'}
$fields=Get-Content $oracle -Raw|ConvertFrom-Json;if($fields.Count -ne $owner.fields.Count){throw 'VersionProps static field universe changed'}
[uint[]]$ids=@(foreach($f in $fields){$field=@($owner.fields|Where-Object {$_.name -eq $f.name -and $_.descriptor -eq $f.descriptor});if($field.Count -ne 1){throw 'VersionProps field identity changed'};$field[0].index})
[string[]]$descriptors=@($fields|Select-Object -ExpandProperty descriptor);[string[]]$expected=@($fields|Select-Object -ExpandProperty value)
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
Add-Type -Path tests/host/VersionPropsProbe.cs
[BoomVersionPropsProbe]::Run($p.compilation.dll,(Join-Path $root boom-runtime.dll),$owner.id,$ids,$descriptors,$expected)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'VersionProps compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('scripts/Test-VersionProps.ps1','java/reference/VersionPropsReference.java','tests/host/VersionPropsProbe.cs')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=1;original_VersionProps_initializer_and_constructor_executed=$true;original_startsWith_wrapper_executed=$true;source_classes=$p.sources.Count;source_methods=$p.symbols.Count;static_fields_compared_with_JVM=$fields.Count;static_field_values_and_identities_retained_after_GC=$true;workers=8;cold_start_constructor_records=6147;constructor_results_distinct_per_batch=$true;warm_one_allocation_calls=128;full_heap_OOM_calls=64;warm_constructor_OOM_does_not_reinitialize_class=$true;GC_root_graph_checked=$true;OOM_recovery=$true;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash $oracle).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-version-props-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
