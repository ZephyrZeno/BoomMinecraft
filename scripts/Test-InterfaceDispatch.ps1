param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$compilerSha=(Get-FileHash $boomPath).Hash.ToLowerInvariant()
$root=Join-Path $projectRoot ('.boom\interface-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\dispatch') -Filter '*.java' -File -Recurse|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Interface fixture javac failed.'}
# Deliberate linkage-error fixture: keep Pending abstract and give Gap a
# concrete class flag without an implementation of the inherited abstract f.
# The isolated JVM below must accept construction and throw AbstractMethodError.
$gap=Join-Path $classes 'dev\boom\dispatch\Gap.class'
$gapBytes=[IO.File]::ReadAllBytes($gap);$cpCount=([int]$gapBytes[8] -shl 8) -bor $gapBytes[9];$offset=10
for($i=1;$i -lt $cpCount;$i++){
    $tag=$gapBytes[$offset];$offset++
    switch($tag){
        1 {$n=([int]$gapBytes[$offset] -shl 8) -bor $gapBytes[$offset+1];$offset+=2+$n}
        {$_ -in @(3,4)} {$offset+=4}
        {$_ -in @(5,6)} {$offset+=8;$i++}
        {$_ -in @(7,8,16,19,20)} {$offset+=2}
        {$_ -in @(9,10,11,12,17,18)} {$offset+=4}
        15 {$offset+=3}
        default {throw 'Unexpected Gap constant tag'}
    }
}
$access=([int]$gapBytes[$offset] -shl 8) -bor $gapBytes[$offset+1]
if(($access -band 0x400) -eq 0){throw 'Gap fixture was not abstract before patch'}
$access=$access -band 0xfbff;$gapBytes[$offset]=[byte]($access -shr 8);$gapBytes[$offset+1]=[byte]($access -band 255)
[IO.File]::WriteAllBytes($gap,$gapBytes)
$gapOracle=Join-Path $root 'GapOracle.java'
[IO.File]::WriteAllText($gapOracle,@'
package dev.boom.dispatch;
public final class GapOracle {
    public static void main(String[] args) throws Exception {
        Root value=(Root)Class.forName("dev.boom.dispatch.Gap").getDeclaredConstructor().newInstance();
        try { value.f(7); throw new AssertionError("Missing method unexpectedly executed"); }
        catch(AbstractMethodError expected) { System.out.print("java.lang.AbstractMethodError"); }
    }
}
'@,[Text.UTF8Encoding]::new($false))
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -cp $classes -d $classes $gapOracle
if($LASTEXITCODE -ne 0){throw 'Gap JVM reference javac failed'}
$gapInfo=[Diagnostics.ProcessStartInfo]::new();$gapInfo.FileName=$tools.java;$gapInfo.UseShellExecute=$false;$gapInfo.CreateNoWindow=$true;$gapInfo.RedirectStandardOutput=$true;$gapInfo.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.dispatch.GapOracle')){$gapInfo.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$gapInfo.Environment.Remove($key)|Out-Null}
$gapProcess=[Diagnostics.Process]::new();$gapProcess.StartInfo=$gapInfo
try{
    if(-not $gapProcess.Start()){throw 'Gap JVM reference did not start'};$gapOut=$gapProcess.StandardOutput.ReadToEndAsync();$gapError=$gapProcess.StandardError.ReadToEndAsync()
    if(-not $gapProcess.WaitForExit(30000)){throw 'Gap JVM reference timed out'}
    if($gapProcess.ExitCode -ne 0 -or $gapOut.GetAwaiter().GetResult() -ne 'java.lang.AbstractMethodError'){throw ('Gap JVM behavior mismatch: '+$gapError.GetAwaiter().GetResult())}
}finally{if(-not $gapProcess.HasExited){$gapProcess.Kill($true);$gapProcess.WaitForExit()};$gapProcess.Dispose()}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$baseArgs=@('compile-program','--entry-class','dev/boom/dispatch/DispatchEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\dispatch') -Filter '*.class' -File -Recurse){$baseArgs+=@('--class-file',$file.FullName)}
$methods=@('choose','nested','wide','reference','nil','initialization','direct','external');$programs=@{}
foreach($method in $methods){
    $text=& $boomPath @baseArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Interface program compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program
    if($program.schema -ne 8 -or $program.interface_dispatch.Count -eq 0 -or $program.full_game_ready){throw 'Unexpected interface dispatch manifest.'}
    Write-Output "Compiled interface entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$value){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
foreach($kind in @(-1,0,1,2,3,4,7,[int]::MinValue,[int]::MaxValue)){
    foreach($value in @(-1,0,1,7,[int]::MinValue,[int]::MaxValue)){
        foreach($method in @('choose','nested','reference')){$cases.Add([pscustomobject]@{method=$method;values=@((Bits $kind),(Bits $value))})}
    }
    foreach($n in @('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff')){
        foreach($d in @('0','3ff8000000000000','c004000000000000','7ff8000000000000','7ff0000000000000')){$cases.Add([pscustomobject]@{method='wide';values=@((Bits $kind),$n,$d)})}
    }
}
foreach($n in @(-1,0,1,7,[int]::MinValue,[int]::MaxValue)){
    foreach($method in @('nil','initialization','direct','external')){$cases.Add([pscustomobject]@{method=$method;values=@((Bits $n))})}
}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $manifest=$programs[$method].compilation
    $selected=@($cases|Where-Object method -eq $method)
    $lines=@($selected|ForEach-Object{(@('dev.boom.dispatch.DispatchEntry',$method,$manifest.descriptor)+@($_.values)) -join ' '})
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
Add-Type -Path (Join-Path $projectRoot 'tests\host\InterfaceDispatchProbe.cs')
[BoomInterfaceDispatchProbe]::Cold($programs['initialization'].compilation.dll,(Join-Path $root 'boom-runtime.dll'))
$text=& $boomPath @baseArgs --method read --output (Join-Path $root 'read')
if($LASTEXITCODE -ne 0){throw 'Interface receiver compilation failed.'}
$receiver=$text|ConvertFrom-Json
function ClassId([string]$name){return [uint32]@($receiver.classes|Where-Object name -eq "dev/boom/dispatch/$name")[0].id}
if(@($receiver.classes|Where-Object name -eq 'dev/boom/dispatch/Pending').Count){throw 'An abstract class became a concrete dispatch receiver'}
[BoomInterfaceDispatchProbe]::Receivers($receiver.compilation.dll,(Join-Path $root 'boom-runtime.dll'),(ClassId 'Gap'),(ClassId 'Plain'),(ClassId 'B'),$receiver.entry_id)
$report=[ordered]@{backend='boom-interface-program-v8-masm-x64';compiler_sha256=$compilerSha;dispatch_abi=2;runtime_language='assembly';compiled_entries=$methods.Count+1;differential_cases=$cases.Count;native_executions=$cases.Count*2;cold_multicore_records=4099;workers=8;class_over_default=$true;child_default=$true;reabstraction_implemented=$true;nested_interface_calls=$true;private_interface_methods=$true;inherited_nonpublic_declaration_through_public_interface=$true;inherited_default_via_invokevirtual=$true;wide_argument_slot_count=$true;reference_arguments_and_results=$true;null_receiver=$true;default_interface_initialization_order=$true;concrete_missing_method_and_incompatible_receivers=$true;abstract_classes_not_concrete_receivers=$true;gap_jvm_reference='java.lang.AbstractMethodError';superclass_execution=$false;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
if((Get-FileHash $boomPath).Hash.ToLowerInvariant() -ne $compilerSha){throw 'Interface compiler changed during verification'}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
[IO.File]::WriteAllText((Join-Path $projectRoot '.boom/latest-interface-program.txt'),$root,[Text.UTF8Encoding]::new($false))
exit 0
