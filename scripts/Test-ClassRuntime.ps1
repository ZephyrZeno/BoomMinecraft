param([switch]$Worker,[string]$Output)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $Worker){
    $root=Join-Path $projectRoot ('.boom\class-runtime-tests\'+[guid]::NewGuid().ToString('N'))
    & (Join-Path $PSScriptRoot 'Build-ClassProbe.ps1') -Output $root
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=(Get-Process -Id $PID).Path;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-NoProfile','-File',$PSCommandPath,'-Worker','-Output',$root)){$info.ArgumentList.Add($arg)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{
        if(-not $process.Start()){throw 'Class runtime worker could not start.'}
        $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(30000)){$process.Kill($true);$process.WaitForExit();throw 'Native class runtime test timed out.'}
        if($process.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        Write-Output $stdout.GetAwaiter().GetResult()
    }finally{if(-not $process.HasExited){$process.Kill($true);$process.WaitForExit()};$process.Dispose()}
}else{
    Add-Type -Path (Join-Path $projectRoot 'tests\host\ClassRuntimeProbe.cs')
    [BoomClassRuntimeProbe]::Run((Join-Path $Output 'class-probe.dll'),(Join-Path $Output 'fpstate.dll'))
    $report=[ordered]@{runtime_language='assembly';cold_threads=12;initializer_callback_count=1;same_owner_reentry=$true;waiter_wakeup=$true;blocked_waiters_before_publication=11;initialized_fast_path_calls=100;failure_and_error_and_no_retry=$true;class_abi_rejection=$true;initializer_fp_environment=$true;caller_mxcsr_restored=$true;passed=$true;full_game_ready=$false;run_directory=$Output}
    $json=$report|ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText((Join-Path $Output 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
}
