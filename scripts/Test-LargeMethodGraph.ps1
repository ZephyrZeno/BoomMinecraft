param([string]$Boom='target/release/boom.exe',[ValidateRange(1050,2000)][int]$Methods=1100)
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/large-graph-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$source=[Text.StringBuilder]::new();[void]$source.AppendLine('package dev.boom.scale; public final class LargeGraph { public static int run(int index,int seed) { switch(index) {')
for($i=0;$i -lt $Methods;$i++){[void]$source.AppendLine("case ${i}: return f$i(seed);")}
[void]$source.AppendLine('default: return ~seed; } }')
for($i=0;$i -lt $Methods;$i++){[void]$source.AppendLine("private static int f$i(int seed) { return seed * 31 + $i; }")}
[void]$source.AppendLine('}');[IO.File]::WriteAllText("$root/LargeGraph.java",$source.ToString(),[Text.UTF8Encoding]::new($false))
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d "$root/classes" "$root/LargeGraph.java"
if($LASTEXITCODE -ne 0){throw 'Large graph fixture javac failed'}
& $Boom compile-program --class-file "$root/classes/dev/boom/scale/LargeGraph.class" --entry-class dev/boom/scale/LargeGraph --method run --descriptor '(II)I' --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 8;throw 'Large graph compilation failed'}
$p=Get-Content "$root/program/program.json" -Raw|ConvertFrom-Json
if($p.symbols.Count -ne $Methods+1 -or $p.symbols.Count -le 1024){throw 'Large graph was not fully linked'}
Add-Type -Path tests/host/LargeMethodGraphProbe.cs
[BoomLargeMethodGraphProbe]::Run($p.compilation.dll,$Methods)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Large graph compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';linked_Java_methods=$p.symbols.Count;previous_1024_method_limit_exceeded=$true;workers=8;native_cases=8*($Methods+2);all_fanout_targets_and_signed_overflow_checked=$true;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-large-graph-test.txt',$root);Write-Output $json
exit 0
