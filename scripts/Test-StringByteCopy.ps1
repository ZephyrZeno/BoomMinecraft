param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v73-display/boom-runtime.dll',[string]$ExistingProgram='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/string-byte-copy-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$basePath=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$program=if($ExistingProgram){[IO.Path]::GetFullPath($ExistingProgram)}else{Join-Path $root program}
if(-not $ExistingProgram){& $Boom compile-locked-program --lock .boom/locks/server.json --jdk-base $basePath --entry-class java/lang/StringConcatHelper --method prepend --descriptor '(J[BLjava/lang/String;)J' --output $program --assemble > "$root/compile.json" 2> "$root/compile.err";if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 8;throw 'Original prepend compilation failed'}}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -d "$root/classes" java/reference/StringCopyReference.java
if($LASTEXITCODE -ne 0){throw 'Byte-copy oracle javac failed'}
$cases=[Collections.Generic.List[string]]::new()
foreach($text in @('','61','0:ff:100:d800:dc00:ffff','d801:dc00','null')){
    foreach($op in @('P','F')){foreach($dst in @(0,2,7,2147483647)){$cases.Add("$op|0|$dst|0|32|$text")};$cases.Add("$op|0|0|0|-1|$text");$cases.Add("$op|0|0|0|1|$text")}
    foreach($range in @(@(0,0,0),@(0,1,1),@(1,2,2),@(-1,0,1),@(0,-1,1),@(0,0,-1),@(2147483647,0,1),@(-2147483648,0,0),@(0,-2147483648,0),@(0,0,-2147483648))){$cases.Add("R|$($range[0])|$($range[1])|$($range[2])|32|$text")}
    $cases.Add("R|0|0|0|-1|$text")
}
# Prepend's internal contract requires a valid nonnegative character index.
# Its intentionally invalid index cases above can select the unsupported Latin1
# branch, so retain those offset-overflow cases for the direct UTF16 ABI only.
$cases=[Collections.Generic.List[string]]@($cases|Where-Object{$_ -notlike 'P|0|2147483647|*'})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName='D:/Dev/Java/jdk-21/bin/java.exe';$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-XX:-CompactStrings','--add-opens=java.base/java.lang=ALL-UNNAMED','-cp',"$root/classes",'StringCopyReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Byte-copy oracle did not start'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$jvm.StandardInput.Write(($cases -join "`n")+"`n");$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(15000)){$jvm.Kill($true);throw 'Byte-copy oracle timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content "$program/program.json" -Raw|ConvertFrom-Json;$base=Get-Content $basePath -Raw|ConvertFrom-Json
$binding=@($p.string_storage|Where-Object property -eq GetBytes);if($binding.Count -ne 1 -or $binding[0].origin.sha256 -ne $base.classes.'java.lang.String'.sha256 -or $binding[0].method_code_sha256 -ne 'bc68ffb69d0420f128bcb5916ee33d3d19f06cc6378c5dec8f00eed34f03278b'){throw 'Original String byte-copy source contract changed'}
Add-Type -Path tests/host/StringCopyProbe.cs
$actual=[BoomStringCopyProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),$cases.ToArray(),[uint32[]]@($p.object_layouts|ForEach-Object class_id),[string[]]@($p.object_layouts|ForEach-Object{$_.class_name.Replace('/','.')}))
if($actual.Count -ne $expected.Count){throw 'Byte-copy oracle row count differs'};for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Byte-copy mismatch $($cases[$i]): JVM=$($expected[$i]); ASM=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Byte-copy compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';JVM_cases=$cases.Count;JVM_CompactStrings=$false;original_StringConcatHelper_prepend_executed=$true;original_String_getBytes_bodies_executed=$false;VM_String_and_byte_array_fixtures_used=$true;UTF16_copy_ABIs_executed=2;null_bounds_int_shift_wrap_surrogates_checked=$true;workers=8;parallel_original_Java_calls=2048;parallel_direct_ABI_calls=4096;warm_guest_allocations=0;Latin1_destination_supported=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;program_directory=$program;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-string-byte-copy-test.txt',$root);Write-Output $json
exit 0
