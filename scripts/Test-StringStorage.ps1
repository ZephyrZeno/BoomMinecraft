param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/string-storage-tests/'+[guid]::NewGuid().ToString('N'));$classes=Join-Path $root classes;[IO.Directory]::CreateDirectory($classes)|Out-Null
[IO.File]::WriteAllText('.boom/current-string-storage-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/storage/StorageProgram.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Storage javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root > (Join-Path $root runtime-build.log) 2>&1
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root fp-build.log) 2>&1
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/StorageProbe.cs
$methods=@('snapshot','floatBits','doubleBits','rawFloat','rawDouble','canonicalFloat','canonicalDouble','classNames','nullClass');$programs=@{}
foreach($method in $methods){
    $descriptor=switch($method){snapshot{'(Ljava/lang/StringBuilder;)Ljava/lang/String;'}doubleBits{'(J)J'}rawFloat{'(F)I'}rawDouble{'(D)J'}canonicalDouble{'(J)J'}default{'(I)I'}}
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/storage/StorageProgram.class) --entry-class dev/boom/storage/StorageProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root $method) --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 10;throw "Storage compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 37 -or $p.backend -ne 'boom-string-storage-program-v37-masm-x64'){throw 'Storage profile missing'}
    foreach($b in $p.bitcasts){if($b.abi -ne 1 -or $b.origin.sha256 -ne $base.classes.($b.origin.binary_name).sha256){throw 'Bitcast source proof changed'}}
    foreach($b in $p.jdk_bridges){$g=$b.target.generated;if($g.generator -ne 'boom-jdk-bridge' -or $g.abi -ne 1 -or $g.host_sha256 -ne $base.classes.($g.host_class.Replace('/','.')).sha256){throw 'Original Java bridge source changed'}}
    if($method -eq 'snapshot'){if($p.builder_snapshot.origin.sha256 -ne $base.classes.'java.lang.StringBuilder'.sha256 -or $p.builder_snapshot.abstract_origin.sha256 -ne $base.classes.'java.lang.AbstractStringBuilder'.sha256 -or $p.builder_snapshot.native_source_sha256 -ne (Get-FileHash native/runtime/builder_snapshot.asm).Hash.ToLowerInvariant() -or $p.builder_snapshot.payload_bytes -ne 14){throw 'Original builder field layout changed'}}
    $programs[$method]=$p;Write-Output "Compiled VM storage/bitcast/original Java bridge: $method"
}
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/StringUTF16 --method length --descriptor '([B)I' --output (Join-Path $root length) --assemble > (Join-Path $root length-compile.json) 2> (Join-Path $root length-compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root length-compile.err) -Tail 10;throw 'Original UTF16.length compilation failed'}
$p=Get-Content (Join-Path $root length/program.json) -Raw|ConvertFrom-Json;$programs.length=$p
if($p.schema -ne 37 -or @($p.string_storage|Where-Object {$_.property -eq 'BigEndian' -and $_.value -eq 0}).Count -ne 1){throw 'Private VM endian binding missing'}
function Java([string]$text){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Storage JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($text).Wait(15000)){throw 'Storage JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Storage JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$ints=[Collections.Generic.List[string]]::new();foreach($v in @('0','1','80000000','ffffffff','7f800000','ff800000','7f800001','7fc12345','ff812345','7fffff','800000','807fffff')){$ints.Add($v)}
$longs=[Collections.Generic.List[string]]::new();foreach($v in @('0','1','8000000000000000','ffffffffffffffff','7ff0000000000000','fff0000000000000','7ff0000000000001','7ff8123456789abc','fff0123456789abc','fffffffffffff','10000000000000','800fffffffffffff')){$longs.Add($v)}
[uint64]$seed=0x12345678;for($i=0;$i -lt 256;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$ints.Add($seed.ToString('x'));$hi=$seed;$seed=($seed*1664525+1013904223) -band 0xffffffffL;$longs.Add($hi.ToString('x8')+$seed.ToString('x8'))}
$cases=@{};foreach($method in $methods|Where-Object {$_ -ne 'snapshot'}){$cases[$method]=if($method -in @('doubleBits','rawDouble','canonicalDouble')){$longs}else{$ints}}
$numeric=@($methods|Where-Object {$_ -ne 'snapshot'});$lines=@(foreach($method in $numeric){$d=$programs[$method].compilation.descriptor;foreach($v in $cases[$method]){'dev.boom.storage.StorageProgram '+$method+' '+$d+' '+$v}})
# Compilation descriptors are source descriptors; assert them rather than guessing argument kinds.
if(@($numeric|Where-Object {-not $programs[$_].compilation.descriptor}).Count){throw 'Storage source descriptor missing'}
$expected=@((Java (($lines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()});if($expected.Count -ne $lines.Count){throw 'Storage oracle count mismatch'}
$index=0;foreach($method in $numeric){$d=$programs[$method].compilation.descriptor;$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root fpstate.dll),[string[]]$cases[$method],$d[$d.Length-1],$true);foreach($v in $actual){if($v -ne $expected[$index]){throw "Storage JVM mismatch: $method at $index, native=$v, JVM=$($expected[$index])"};$index++};Write-Output "Validated raw/canonical bit semantics or original Class Java body: $method"}
[BoomStorageProbe]::Snapshot($programs.snapshot.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomStorageProbe]::SnapshotOOM($programs.snapshot.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomStorageProbe]::Length($programs.length.compilation.dll,(Join-Path $root boom-runtime.dll))
$owner=@($programs.length.classes|Where-Object name -eq 'java/lang/StringUTF16')[0];$hi=@($owner.fields|Where-Object name -eq 'HI_BYTE_SHIFT')[0];$lo=@($owner.fields|Where-Object name -eq 'LO_BYTE_SHIFT')[0]
[BoomStorageProbe]::EndianFields($programs.length.compilation.dll,(Join-Path $root boom-runtime.dll),$owner.id,$hi.index,$lo.index)
$parallelLines=@(foreach($i in 0..2048){'dev.boom.storage.StorageProgram classNames (I)I '+$i.ToString('x')});$parallelExpected=@((Java (($parallelLines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Trim().Substring(2),16)),0)})
[BoomStorageProbe]::ClassParallel($programs.classNames.compilation.dll,(Join-Path $root boom-runtime.dll),[int[]]$parallelExpected)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Storage compiler changed'}
$sources=[ordered]@{};foreach($path in @('native/runtime/builder_snapshot.asm','java/subset/dev/boom/storage/StorageProgram.java','tests/host/StorageProbe.cs','scripts/Test-StringStorage.ps1','src/compiler/jdk_bridges.rs')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{backend='boom-string-storage-program-v37-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=10;JVM_differential_cases=$lines.Count;native_differential_calls=($lines.Count*2);raw_NaN_payloads_and_canonical_wrappers=$true;original_Class_toString_bytecode_retained=$true;class_primitive_interface_and_array_names=$true;copied_original_Code_and_source_origin=$true;UTF16_length_cases=129;original_UTF16_initializer_shift_fields_verified=$true;builder_snapshot_inputs='VM-prepared valid original-layout objects; original builder constructor not executed';builder_snapshot_fresh_copy_and_mutation_isolation=$true;builder_snapshot_latin1_and_UTF16=$true;builder_snapshot_partial_OOM_and_recovery=$true;builder_layout_payload_bytes=14;compact_flag_compiles_to_VM_UTF16_configuration=$true;compact_flag_runtime_path_verified=$false;workers=8;multicore_records=6147;automatic_gc=$false;StringBuilder_constructor_and_append_complete=$false;Object_toString_complete=$false;String_valueOf_Object_complete=$false;full_game_ready=$false;sources=$sources;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-string-storage-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
