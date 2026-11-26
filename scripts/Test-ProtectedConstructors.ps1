param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/protected-constructor-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-protected-constructor-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
$java=$inputs.java.executable;$javac=Join-Path (Split-Path $java) javac.exe
$sources=@('java/subset/dev/boom/access/parent/ProtectedBase.java','java/subset/dev/boom/access/child/ConstructorProgram.java','java/subset/dev/boom/access/grandchild/Grandchild.java','java/subset/dev/boom/access/ConstructorReference.java')
& $javac --release 21 -g -proc:none -encoding UTF-8 -d $classes @sources
if($LASTEXITCODE -ne 0){throw 'Protected constructor javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/CloneProbe.cs
$common=@('compile-program','--entry-class','dev/boom/access/child/ConstructorProgram','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($f in Get-ChildItem (Join-Path $classes dev/boom/access) -Filter *.class -Recurse){$common+=@('--class-file',$f.FullName)}
$programs=@{}
foreach($method in @('child','wide','anonymous','chained','enumValues')){
    $descriptor=if($method -eq 'wide'){'(I)J'}else{'(I)I'}
    $out=Join-Path $root $method
    & $Boom @common --method $method --descriptor $descriptor --output $out > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 12;throw "Protected constructor compile failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 42 -or $p.protected_constructors.Count -eq 0 -or $p.full_game_ready){throw 'Protected constructor source binding missing'}
    foreach($b in $p.protected_constructors){
        if($b.abi -ne 1 -or ($b.access -band 0x50f) -ne 4 -or $b.superclass_chain.Count -lt 2 -or $b.superclass_chain[0].sha256 -ne $b.caller.sha256 -or $b.superclass_chain[-1].sha256 -ne $b.owner.sha256 -or $b.receiver_rule -ne 'initialized-receiver-type-assignable-to-current-class'){throw 'Protected constructor receiver/ancestry proof missing'}
        foreach($origin in $b.superclass_chain){if(@($p.sources|Where-Object {$_.origin.sha256 -eq $origin.sha256 -and $_.origin.loader -eq $origin.loader -and $_.origin.binary_name -eq $origin.binary_name}).Count -ne 1){throw 'Constructor ancestry differs from executable sources'}}
    }
    $programs[$method]=$p
    Write-Output "Compiled protected constructor path: $method"|Out-Host
}
$enum=$programs.enumValues
if(@($enum.symbols|Where-Object {$_.class_name -eq 'java/lang/Enum' -and $_.method -eq '<init>' -and $_.descriptor -eq '(Ljava/lang/String;I)V'}).Count -ne 1 -or @($enum.protected_constructors|Where-Object {$_.owner.binary_name -eq 'java.lang.Enum' -and $_.owner.loader -eq 'bootstrap'}).Count -ne 1 -or $enum.array_clones.Count -eq 0){throw 'Original Enum constructor or generated values clone missing'}
function Java([string]$method,[string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.access.ConstructorReference',$method)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{
        if(-not $process.Start()){throw 'Constructor JVM reference failed'}
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(15000)){throw 'Constructor reference input stalled'}
        $process.StandardInput.Close();if(-not $process.WaitForExit(30000)){throw 'Constructor reference timed out'}
        if($process.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $process.HasExited){$process.Kill($true);$process.WaitForExit()};$process.Dispose()}
}
$cases=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt 32;$i++){$cases.Add($i.ToString('x8'))}
foreach($v in @('ffffffff','80000000','7fffffff','12345678')){$cases.Add($v)}
$random=[Random]::new(42042);$bytes=[byte[]]::new(4)
while($cases.Count -lt 272){$random.NextBytes($bytes);$cases.Add([BitConverter]::ToUInt32($bytes,0).ToString('x8'))}
$count=0
foreach($method in @('child','wide','anonymous','chained','enumValues')){
    $p=$programs[$method];$kind=if($method -eq 'wide'){'J'}else{'I'}
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root fpstate.dll),$cases.ToArray(),$kind,$true)
    $expected=Java $method $cases.ToArray()
    [IO.File]::WriteAllLines((Join-Path $root ($method+'-native.txt')),[string[]]$actual,[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllLines((Join-Path $root ($method+'-reference.txt')),[string[]]$expected,[Text.UTF8Encoding]::new($false))
    if($actual.Count -ne 272 -or $expected.Count -ne 272 -or ($actual -join '|') -cne ($expected -join '|')){throw "Constructor/JVM mismatch: $method"}
    $count+=$actual.Count
}
[string[]]$workerCases=@(0..2048|ForEach-Object{$_.ToString('x8')})
[int[]]$workerExpected=@((Java enumValues $workerCases)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomCloneProbe]::Parallel($enum.compilation.dll,(Join-Path $root boom-runtime.dll),$workerExpected)

# Compile the callers against public constructors, then restore restrictive
# definitions. Both the JVM and AOT backend must reject these linked inputs.
$bad=Join-Path $root bad;$badClasses=Join-Path $bad classes
[IO.Directory]::CreateDirectory($bad)|Out-Null
$original=[IO.File]::ReadAllText($sources[0])
[IO.File]::WriteAllText((Join-Path $bad ProtectedBase.java),$original.Replace('protected ProtectedBase','public ProtectedBase'))
[IO.File]::WriteAllText((Join-Path $bad IllegalNew.java),'package dev.boom.access.bad; import dev.boom.access.parent.ProtectedBase; public final class IllegalNew extends ProtectedBase { public IllegalNew(){super(0);} public static int run(int v){return new ProtectedBase(v).value();}}')
[IO.File]::WriteAllText((Join-Path $bad Unrelated.java),'package dev.boom.access.bad; import dev.boom.access.parent.ProtectedBase; public final class Unrelated { public static int run(int v){return new ProtectedBase(v).value();}}')
[IO.File]::WriteAllText((Join-Path $bad BadReference.java),'package dev.boom.access.bad; public final class BadReference {public static void main(String[] a)throws Exception{Class.forName(a[0]).getMethod("run",int.class).invoke(null,17);}}')
& $javac --release 21 -g -proc:none -d $badClasses (Join-Path $bad ProtectedBase.java) (Join-Path $bad IllegalNew.java) (Join-Path $bad Unrelated.java) (Join-Path $bad BadReference.java)
if($LASTEXITCODE -ne 0){throw 'Negative constructor fixture javac failed'}
$rejections=[Collections.Generic.List[object]]::new()
foreach($test in @(@('protected','IllegalNew','Protected constructor receiver'),@('protected','Unrelated','not a subclass'),@('private','IllegalNew','Member access denied'),@('nonpublic','IllegalNew','access denied|nonpublic'))){
    $mode=$test[0];$name=$test[1];$variant=Join-Path $bad $mode;[IO.Directory]::CreateDirectory($variant)|Out-Null
    $text=switch($mode){private{$original.Replace('protected ProtectedBase','private ProtectedBase')};nonpublic{$original.Replace('public class ProtectedBase','class ProtectedBase')};default{$original}}
    [IO.File]::WriteAllText((Join-Path $variant ProtectedBase.java),$text)
    & $javac --release 21 -g -proc:none -d $variant (Join-Path $variant ProtectedBase.java)
    if($LASTEXITCODE -ne 0){throw 'Restrictive constructor javac failed'}
    Copy-Item (Join-Path $variant dev/boom/access/parent/ProtectedBase.class) (Join-Path $badClasses dev/boom/access/parent/ProtectedBase.class) -Force
    $badCommon=@('compile-program','--entry-class',('dev/boom/access/bad/'+$name),'--method','run','--descriptor','(I)I','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
    foreach($f in Get-ChildItem $badClasses -Filter *.class -Recurse){$badCommon+=@('--class-file',$f.FullName)}
    $out=Join-Path $bad ($mode+'-'+$name)
    $reason=(& $Boom @badCommon --output $out 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or $reason -notmatch $test[2] -or (Test-Path (Join-Path $out program.json))){throw "Illegal constructor input accepted: $mode/$name ($reason)"}
    $jvm=(& $java -Xverify:all -cp $badClasses dev.boom.access.bad.BadReference ('dev.boom.access.bad.'+$name) 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or $jvm -notmatch 'VerifyError|IllegalAccessError'){throw 'JVM did not reject restrictive constructor input'}
    [IO.File]::WriteAllText((Join-Path $bad ($mode+'-'+$name+'-aot.txt')),$reason)
    [IO.File]::WriteAllText((Join-Path $bad ($mode+'-'+$name+'-jvm.txt')),$jvm)
    $rejections.Add([ordered]@{mode=$mode;caller=$name;aot_rejected=$true;JVM_rejected=$true;reason=$reason})
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Constructor compiler changed during verification'}
$hashes=[ordered]@{}
foreach($path in @($sources)+@('src/compiler/protected_constructors.rs','tests/host/CloneProbe.cs','scripts/Test-ProtectedConstructors.ps1')){$hashes[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;compiled_entries=5;JVM_differential_cases=$count;native_differential_calls=$count*2;runtime_language='assembly';original_Enum_constructor_Code_executed=$true;javac_generated_values_clone_executed=$true;private_Enum_fields_and_actual_constant_identity=$true;anonymous_subclass_and_two_level_cross_package_chain=$true;wide_arguments_and_this_delegation=$true;receiver_and_access_rejections=$rejections.ToArray();workers=8;multicore_records=6147;quiescent_GC_graph_verified=$true;automatic_gc=$false;general_cross_package_protected_fields_and_methods=$false;full_game_ready=$false;passed=$true;sources=$hashes;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-protected-constructor-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
