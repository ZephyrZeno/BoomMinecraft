param([string]$Lock='.boom\locks\client.json',[Parameter(Mandatory=$true)][string]$JdkBase,[string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $projectRoot ('.boom\type-runtime-tests\'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$planPath=Join-Path $root 'types.json'
& $Boom plan-types --lock $Lock --jdk-base $JdkBase --class net.minecraft.client.main.Main --class net.minecraft.server.Main --class java.lang.String --class java.lang.Cloneable --type '[[I' --type '[[Ljava/lang/String;' --type '[Ljava/lang/Object;' --type '[Ljava/io/Serializable;' --type '[Z' --type '[B' --type '[S' --type '[J' --type '[F' --type '[D' --output $planPath
if($LASTEXITCODE -ne 0){throw 'Type metadata plan failed.'}
$plan=Get-Content -LiteralPath $planPath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $plan.metadata_assembly -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.metadata_digest.sha256){throw 'Type assembly identity mismatch.'}
$inputs=Get-Content -LiteralPath $Lock -Raw|ConvertFrom-Json
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\TypeOracle.java')
if($LASTEXITCODE -ne 0){throw 'Type oracle javac failed.'}
$script:typeNames=@{}
function TypeName([int]$id){
    if($script:typeNames.ContainsKey($id)){return $script:typeNames[$id]}
    $type=$plan.types[$id]
    $name=switch($type.kind){
        'primitive' { $type.value.ToLowerInvariant() }
        'class' {$type.key.name.Replace('/','.')}
        'array' {
            $component=$plan.types[$type.component]
            if($component.kind -eq 'primitive'){'['+(@{Boolean='Z';Byte='B';Char='C';Short='S';Int='I';Long='J';Float='F';Double='D'}[$component.value])}
            elseif($component.kind -eq 'array'){'['+(TypeName $type.component)}
            else{'[L'+(TypeName $type.component)+';'}
        }
    }
    $script:typeNames[$id]=$name;return $name
}
$lines=[Collections.Generic.List[string]]::new()
for($from=0;$from -lt $plan.types.Count;$from++){for($to=0;$to -lt $plan.types.Count;$to++){$lines.Add((TypeName $from)+' '+(TypeName $to))}}
$paths=@($inputs.classpath|ForEach-Object{$id=$_;($inputs.files|Where-Object id -eq $id).path})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',((@($classes)+$paths) -join ';'),'dev.boom.subset.TypeOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Type oracle start failed.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Type oracle input stalled.'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Type oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    [int[]]$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[int]$_.Trim()})
    if($expected.Count -ne $lines.Count){throw 'Type oracle output count mismatch.'}
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$(Join-Path $root 'metadata.obj')" $plan.metadata_assembly
if($LASTEXITCODE -ne 0){throw 'Type metadata assembly failed.'}
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$(Join-Path $root 'type-probe.obj')" (Join-Path $projectRoot 'native\probe\types.asm')
if($LASTEXITCODE -ne 0){throw 'Type probe assembly failed.'}
$dll=Join-Path $root 'type-probe.dll'
& (Join-Path $bin 'link.exe') /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /EXPORT:boom_type_assignable /EXPORT:boom_get_type_descriptor /EXPORT:boom_get_type_count /EXPORT:boom_type_probe_entry "/OUT:$dll" (Join-Path $root 'metadata.obj') (Join-Path $root 'types.obj') (Join-Path $root 'type-probe.obj')
if($LASTEXITCODE -ne 0){throw 'Type probe link failed.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\TypeRuntimeProbe.cs')
[BoomTypeRuntimeProbe]::Run($dll,(Join-Path $root 'boom-runtime.dll'),$plan.types.Count,$expected)
$tampered=Join-Path $root 'tampered';$stringDir=Join-Path $tampered 'image\java.base\java\lang';[IO.Directory]::CreateDirectory($stringDir)|Out-Null
Copy-Item -LiteralPath $JdkBase -Destination (Join-Path $tampered 'jdk-base.json')
$stringSource=Join-Path (Split-Path -Parent $JdkBase) 'image\java.base\java\lang\String.class'
$bytes=[IO.File]::ReadAllBytes($stringSource);$bytes[$bytes.Length-1]=$bytes[$bytes.Length-1] -bxor 1
[IO.File]::WriteAllBytes((Join-Path $stringDir 'String.class'),$bytes)
$corrupted=& $Boom plan-types --lock $Lock --jdk-base (Join-Path $tampered 'jdk-base.json') --class java.lang.String --output (Join-Path $tampered 'bad.json') 2>&1
if($LASTEXITCODE -eq 0 -or (($corrupted|ForEach-Object ToString) -join "`n") -notlike '*Cached JDK class changed*'){throw 'Corrupt JDK cache was not rejected.'}
if(Test-Path -LiteralPath (Join-Path $tampered 'bad.json')){throw 'Corrupt JDK cache emitted a type plan.'}
$platform=& $Boom plan-types --lock $Lock --jdk-base $JdkBase --class java.sql.Connection --output (Join-Path $root 'platform.json') 2>&1
if($LASTEXITCODE -eq 0){throw 'Missing JDK platform provider was silently accepted.'}
$report=[ordered]@{runtime_language='assembly';jdk_classes=@((Get-Content -LiteralPath $JdkBase -Raw|ConvertFrom-Json).classes.PSObject.Properties).Count;types=$plan.types.Count;differential_cases=$expected.Count;native_sequential=$expected.Count;native_parallel=$expected.Count*12;worker_counts=@(1,2,4,8);batches_per_worker_count=3;corrupted_jdk_cache_rejected=$true;missing_platform_provider_rejected=$true;vanilla_class_initialization=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
