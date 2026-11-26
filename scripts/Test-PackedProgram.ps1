param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='',[string]$BaselineBoom='.boom\baselines\compiler-v9\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$root=Join-Path $projectRoot ('.boom\packed-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\inheritance') -Filter '*.java' -File -Recurse|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Interface fixture javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$baseArgs=@('compile-program','--entry-class','dev/boom/inheritance/PackedEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\inheritance') -Filter '*.class' -File -Recurse){$baseArgs+=@('--class-file',$file.FullName)}
$methods=@('narrow','adjacent','floatNeighbor','floatValue','longValue','doubleValue');$programs=@{}
foreach($method in $methods){
    $text=& $boomPath @baseArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Packed program compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program
    if($program.schema -ne 10 -or $program.full_game_ready){throw 'Unexpected compact inheritance manifest.'}
    Write-Output "Compiled packed entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$value){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
foreach($n in @(-1,0,1,7,128,255,256,32768,65535,[int]::MinValue,[int]::MaxValue)){
    foreach($method in @('narrow','adjacent')){$cases.Add([pscustomobject]@{method=$method;values=@((Bits $n))})}
    foreach($f in @('0','80000000','3f800000','bf800000','7f800000','ff800000','7fc00000','7f800001','1','7fffff','800000','7f7fffff')){
        foreach($method in @('floatNeighbor','floatValue')){$cases.Add([pscustomobject]@{method=$method;values=@((Bits $n),$f)})}
    }
    foreach($v in @('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','123456789abcdef')){$cases.Add([pscustomobject]@{method='longValue';values=@((Bits $n),$v)})}
    foreach($v in @('0','8000000000000000','3ff8000000000000','c004000000000000','7ff8000000000000','7ff0000000000000','fff0000000000000','1','fffffffffffff','7fefffffffffffff')){$cases.Add([pscustomobject]@{method='doubleValue';values=@((Bits $n),$v)})}
}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $manifest=$programs[$method].compilation
    $selected=@($cases|Where-Object method -eq $method)
    $lines=@($selected|ForEach-Object{(@('dev.boom.inheritance.PackedEntry',$method,$manifest.descriptor)+@($_.values)) -join ' '})
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
    try{
        if(-not $oracle.Start()){throw 'Interface JVM reference failed.'}
        $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
        if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Interface JVM input stalled.'}
        $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Interface JVM reference timed out.'}
        if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
    if($expected.Count -ne $selected.Count){throw 'Interface reference case count mismatch.'}
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Interface module hash mismatch.'}
    [string[]]$values=@($selected|ForEach-Object{$_.values -join ' '})
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$manifest.descriptor[-1],$true)
    for($i=0;$i -lt $selected.Count;$i++){if($actual[$i] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$selected[$i];expected=$expected[$i];actual=$actual[$i]})}}
}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\PackedMemoryProbe.cs')
[BoomPackedMemoryProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
$text=& $boomPath @baseArgs --method writeByte --output (Join-Path $root 'writeByte')
if($LASTEXITCODE -ne 0){throw 'Packed shared byte compilation failed.'}
$shared=$text|ConvertFrom-Json
$layout=@($shared.object_layouts|Where-Object class_name -eq 'dev/boom/inheritance/Dense')[0].layout
function Offset([string]$name){return [int]@($layout.fields|Where-Object{$_.name -eq $name -and $_.declaring_class -eq 'dev/boom/inheritance/Dense'})[0].offset}
[int[]]$flags=@(0..31|ForEach-Object{Offset "f$_"})
if($layout.abi -ne 2 -or $layout.payload_bytes -ne 106 -or (Offset 'right') -ne (Offset 'left')+1){throw 'Unexpected compact Dense shape.'}
[BoomPackedMemoryProbe]::SharedBytes($shared.compilation.dll,(Join-Path $root 'boom-runtime.dll'),(Offset 'left'),(Offset 'right'),$flags,106)
$baselinePath=(Resolve-Path -LiteralPath $BaselineBoom).Path
$baselineReceipt=Get-Content -LiteralPath (Join-Path (Split-Path -Parent $baselinePath) 'manifest.json') -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $baselinePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $baselineReceipt.sha256){throw 'Baseline compiler identity mismatch.'}
$memory=[ordered]@{}
foreach($family in @('grand','dense')){
    $entry=if($family -eq 'grand'){'dev/boom/inheritance/InheritanceEntry'}else{'dev/boom/inheritance/PackedEntry'}
    $method=if($family -eq 'grand'){'pick'}else{'make'}
    $factoryArgs=@('compile-program','--entry-class',$entry,'--method',$method,'--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
    foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\inheritance') -Filter '*.class' -File -Recurse){$factoryArgs+=@('--class-file',$file.FullName)}
    $text=& $baselinePath @factoryArgs --output (Join-Path $root "legacy-$family")
    if($LASTEXITCODE -ne 0){throw "Legacy factory compilation failed: $family"};$legacy=$text|ConvertFrom-Json
    $text=& $boomPath @factoryArgs --output (Join-Path $root "compact-$family")
    if($LASTEXITCODE -ne 0){throw "Compact factory compilation failed: $family"};$packed=$text|ConvertFrom-Json
    if($legacy.schema -ne 9 -or $packed.schema -ne 10){throw 'Factory comparison backend mismatch.'}
    if($legacy.sources.Count -ne $packed.sources.Count){throw 'Factory input sets differ.'}
    foreach($source in $legacy.sources){if(@($packed.sources|Where-Object{$_.class_name -eq $source.class_name -and $_.digest.sha256 -eq $source.digest.sha256}).Count -ne 1){throw 'Factory comparison changed Java input.'}}
    foreach($program in @($legacy,$packed)){if((Get-FileHash -LiteralPath $program.compilation.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $program.compilation.dll_digest.sha256){throw 'Factory DLL identity changed.'}}
    $objects=if($family -eq 'grand'){4}else{3};$oldPayload=if($family -eq 'grand'){80}else{376};$newPayload=if($family -eq 'grand'){58}else{106}
    $old=[BoomPackedMemoryProbe]::Measure($legacy.compilation.dll,8195,$objects,$oldPayload,1,($family -eq 'grand'))
    $new=[BoomPackedMemoryProbe]::Measure($packed.compilation.dll,8195,$objects,$newPayload,2,($family -eq 'grand'))
    $capacity=@{}
    foreach($budget in @(4096,8192)){
        $oldCount=[BoomPackedMemoryProbe]::Capacity($legacy.compilation.dll,$budget,$objects,($family -eq 'grand'))
        $newCount=[BoomPackedMemoryProbe]::Capacity($packed.compilation.dll,$budget,$objects,($family -eq 'grand'))
        if($newCount -le $oldCount){throw 'Compact layouts did not increase fixed-budget capacity.'}
        $capacity["$budget"]=[ordered]@{legacy_graphs=$oldCount;compact_graphs=$newCount}
    }
    if($new.reserved_bytes -ge $old.reserved_bytes){throw 'Compact layout did not reduce actual arena occupancy.'}
    $memory[$family]=[ordered]@{legacy=$old;compact=$new;arena_bytes_saved=$old.reserved_bytes-$new.reserved_bytes;arena_reduction_percent=100.0*(1.0-$new.reserved_bytes/[double]$old.reserved_bytes);capacity=$capacity}
}
$report=[ordered]@{backend='boom-compact-program-v10-masm-x64';runtime_language='assembly';object_layout_abi=2;compiled_differential_entries=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;shared_adjacent_byte_records=65539;workers=8;unknown_layout_abi_rejected=$true;reference_prefix_preserved=$true;memory_comparison=$memory;scope='Allocator arena occupancy with identical Java bytecode; fixed heap OS reservation is unchanged';failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 12
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
