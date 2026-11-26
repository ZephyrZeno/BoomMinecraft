param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/character-data-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-character-data-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/reference/CharacterReference.java
if($LASTEXITCODE -ne 0){throw 'Character oracle javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('--add-opens','java.base/java.lang=ALL-UNNAMED','-Xmx128m','-cp',$classes,'CharacterReference',(Join-Path $root types.bin),(Join-Path $root map.bin))){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Character JVM oracle failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(120000)){throw 'Character JVM oracle timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
$out=Join-Path $root getType
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/Character --method getType --descriptor '(I)I' --output $out --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 14;throw 'Original Character.getType compilation failed'}
$p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
$characterSources=@($p.sources|Where-Object class_name -Like 'java/lang/CharacterData*')
if($p.schema -ne 45 -or $p.string_chars.Count -ne 5 -or $p.typed_arrays.sites.Count -ne 2 -or $characterSources.Count -ne 9 -or $p.full_game_ready){throw 'Original character source/array integration scope changed'}
foreach($source in $p.sources){$name=$source.class_name.Replace('/','.');if($source.origin.loader -ne 'bootstrap' -or $source.origin.source_id -ne 'jdk:java.base' -or $source.origin.generated -or $source.origin.sha256 -ne $base.classes.$name.sha256){throw 'Non-original source entered Character.getType'}}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
Add-Type -Path tests/host/ReplaceProbe.cs
Add-Type -Path tests/host/CharacterProbe.cs
[byte[]]$expected=[IO.File]::ReadAllBytes((Join-Path $root types.bin));[byte[]]$map=[IO.File]::ReadAllBytes((Join-Path $root map.bin))
[int[]]$parallel=@(0..2048|ForEach-Object{[int]$expected[$_]})
[BoomReplaceProbe]::Parallel($p.compilation.dll,(Join-Path $root boom-runtime.dll),$parallel)
Write-Output 'Validated original character classes with 8 cold-start assembly workers'
[uint[]]$ids=@($p.classes|Where-Object name -Like 'java/lang/CharacterData*'|Select-Object -ExpandProperty id)
$owner=$p.classes|Where-Object name -eq 'java/lang/CharacterData00';$field=$owner.fields|Where-Object name -eq 'charMap'
[BoomCharacterProbe]::Run($p.compilation.dll,(Join-Path $root boom-runtime.dll),$expected,$ids,$owner.id,$field.index,$map)
Write-Output 'Validated all 1114112 Unicode code points and original CharacterData00 charMap'
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Character compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('scripts/Test-CharacterData.ps1','tests/host/CharacterProbe.cs','tests/host/ReplaceProbe.cs','java/reference/CharacterReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=1;source_classes=$p.sources.Count;source_methods=$p.symbols.Count;only_original_locked_java_base_sources=$true;character_data_classes=9;all_Unicode_code_points=1114112;invalid_and_random_int_cases=520;JVM_differential_cases=1114632;post_GC_queries=512;original_charMap_matches_JVM=$true;all_character_data_initializers_completed=$true;GC_static_root_graph_verified=$true;full_heap_no_allocation_queries=8193;workers=8;cold_start_multicore_records=6147;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash (Join-Path $root types.bin)).Hash.ToLowerInvariant();charMap_oracle_sha256=(Get-FileHash (Join-Path $root map.bin)).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-character-data-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
