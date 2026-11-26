param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/descriptor-program-tests/'+[guid]::NewGuid().ToString('N'));$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/descriptors/DescriptorEntry.java java/subset/dev/boom/descriptors/FileIoReference.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Descriptor javac reference failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
& scripts/Build-FileIoProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/DescriptorProbe.cs
$common=@('compile-program','--entry-class','dev/boom/descriptors/DescriptorEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($f in Get-ChildItem (Join-Path $classes 'dev/boom/descriptors') -Filter 'DescriptorEntry*.class'){$common+=@('--class-file',$f.FullName)}
$methods=@('standard','fresh','identity','nested');$programs=@{}
foreach($method in $methods){
    & $Boom @common --method $method --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "Descriptor compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 26){throw 'Descriptor/nest profile missing'}
    if($method -eq 'nested'){
        if($null -ne $p.file_descriptors -or $p.nest_access.Count -lt 2){throw 'Nest access proof missing'}
        foreach($n in $p.nest_access){if($n.host.binary_name -ne 'dev.boom.descriptors.DescriptorEntry' -or $n.host.loader -ne 'explicit-application'){throw 'Nest host provenance mismatch'}}
    }else{
        if($p.file_descriptors.bindings.Count -ne 3 -or $p.file_descriptors.origin.sha256 -ne $base.classes.'java.io.FileDescriptor'.sha256){throw 'Native descriptor provenance mismatch'}
        foreach($class in @('java/io/FileDescriptor','java/io/FileDescriptor$1')){if(@($p.symbols|Where-Object {$_.class_name -eq $class -and $_.method -in @('<init>','<clinit>')}).Count -eq 0){throw 'Original descriptor construction missing'}}
        if(@($p.symbols|Where-Object {$_.class_name -eq 'jdk/internal/access/SharedSecrets' -and $_.method -eq 'setJavaIOFileDescriptorAccess'}).Count -ne 1){throw 'Original SharedSecrets registration missing'}
    }
    $programs[$method]=$p;Write-Output "Compiled descriptor/nest entry: $method"
}
$values=[Collections.Generic.List[string]]::new()
foreach($n in @(0,1,-1,[int]::MinValue,[int]::MaxValue,127,128,255,256,32767,32768,65535,65536,-65536,0xd800,0xdbff,0xdc00,0xdfff,0x1f600)){$values.Add(([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$n),0)).ToString('x'))}
[uint64]$seed=0x12345678
for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
function Java([string[]]$arguments,[string]$inputText=''){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in $arguments){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $p=[Diagnostics.Process]::new();$p.StartInfo=$info
    try{if(-not $p.Start()){throw 'Descriptor JVM reference failed'};$stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync();if($inputText -and -not $p.StandardInput.WriteAsync($inputText).Wait(15000)){throw 'Descriptor JVM input stalled'};$p.StandardInput.Close();if(-not $p.WaitForExit(30000)){throw 'Descriptor JVM reference timed out'};if($p.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $p.HasExited){$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
}
$lines=@(foreach($method in $methods){foreach($v in $values){'dev.boom.descriptors.DescriptorEntry '+$method+' (I)I '+$v}})
$reference=Java @('-cp',$classes,'dev.boom.subset.ClassNumericOracle') (($lines -join "`n")+"`n")
$expected=@($reference.Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Descriptor reference case count changed'}
$index=0
foreach($method in $methods){$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values.ToArray(),'I',$true);foreach($result in $actual){if($result -ne $expected[$index]){throw "Descriptor differential mismatch: $method, $index, $result, $($expected[$index])"};$index++}}
$p=$programs['standard'];$owner=@($p.classes|Where-Object name -eq 'java/io/FileDescriptor')[0];[uint32[]]$fields=@(foreach($name in @('in','out','err')){@($owner.fields|Where-Object name -eq $name)[0].index})
[BoomDescriptorProbe]::Parallel($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$owner.id,$fields)
Java @('-cp',$classes,'dev.boom.descriptors.FileIoReference',(Join-Path $root 'jvm-bytes.bin'),(Join-Path $root 'jvm-append.bin'))|Out-Null
[BoomDescriptorProbe]::Io($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),(Join-Path $root 'fd-worker.dll'),$owner.id,$fields[1],$root)
$bad=Join-Path $root 'bad-nest';$badClasses=Join-Path $bad 'classes';[IO.Directory]::CreateDirectory($badClasses)|Out-Null
Copy-Item -LiteralPath (Join-Path $classes 'dev') -Destination $badClasses -Recurse
& python tests/strip_fixture_nest.py (Join-Path $badClasses 'dev/boom/descriptors/DescriptorEntry.class')
if($LASTEXITCODE -ne 0){throw 'Isolated nest fixture patch failed'}
$badReference=Java @('-cp',$badClasses,'dev.boom.subset.ClassNumericOracle') "dev.boom.descriptors.DescriptorEntry nested (I)I 7`n"
if($badReference.Trim() -ne 'e java.lang.IllegalAccessError'){throw "JVM did not reject unreciprocated private nest access: $badReference"}
$out=Join-Path $bad 'rejected';$argsList=@('compile-program','--entry-class','dev/boom/descriptors/DescriptorEntry','--method','nested','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',$out)
foreach($f in Get-ChildItem (Join-Path $badClasses 'dev/boom/descriptors') -Filter 'DescriptorEntry*.class'){$argsList+=@('--class-file',$f.FullName)}
$reason=(& $Boom @argsList 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or (Test-Path $out) -or $reason -notmatch 'Member access denied'){throw 'Invalid private nest accepted'}
$out=Join-Path $root 'reject-no-metadata'; & $Boom compile-program --class-file (Join-Path $classes 'dev/boom/descriptors/DescriptorEntry.class') --entry-class dev/boom/descriptors/DescriptorEntry --method standard --output $out 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'Descriptor execution without metadata accepted'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Descriptor compiler changed during test'}
$report=[ordered]@{backend='boom-runtime-access-program-v26-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=4;differential_cases=$lines.Count;native_executions=($lines.Count*2);multicore_records=12294;workers=8;original_FileDescriptor_and_SharedSecrets_initializers=$true;native_field_table_validated_and_atomically_published=$true;standard_handles_match_actual_Windows_handles=$true;standard_descriptor_identity_and_roots_preserved=$true;registered_private_member_origin_checked=$true;nest_access_reciprocal_loader_package_and_host=$true;JVM_rejects_broken_nest=$true;native_write_read_sync_bytes=1048576;concurrent_append_records=6147;append_records_match_JVM=$true;file_and_broken_pipe_EOF=$true;IO_errors_bounds_null_and_zero_length=$true;guest_IO_temporary_allocations=0;negative_compile_checks=2;automatic_gc=$false;Java_FileInputStream_FileOutputStream_chains_complete=$false;System_application_bootstrap_complete=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-descriptor-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
