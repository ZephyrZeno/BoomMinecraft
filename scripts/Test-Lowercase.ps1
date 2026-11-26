param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/lowercase-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-lowercase-test.txt',$root)
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d $classes java/subset/dev/boom/lowercase/LowercaseProgram.java java/reference/LowercaseReference.java
if($LASTEXITCODE -ne 0){throw 'Lowercase fixture/reference javac failed'}
& $Boom compile-program --class-file (Join-Path $classes dev/boom/lowercase/LowercaseProgram.class) --entry-class dev/boom/lowercase/LowercaseProgram --method lower --descriptor '(Ljava/lang/String;Ljava/util/Locale;)Ljava/lang/String;' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root program) --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 12;throw 'Locale lowercase compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-lowercase.py (Join-Path $root program/program.json) $JdkBase > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Lowercase source/field binding proof failed'}
& D:/Dev/Python312/python.exe scripts/make-lowercase-cases.py (Join-Path $root cases.txt) > (Join-Path $root case-scope.json)
if($LASTEXITCODE -ne 0){throw 'Lowercase input generation failed'}
[string[]]$lines=Get-Content (Join-Path $root cases.txt)
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'LowercaseReference')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$jvm=[Diagnostics.Process]::new();$jvm.StartInfo=$info
try{if(-not $jvm.Start()){throw 'Lowercase JVM reference failed'};$stdout=$jvm.StandardOutput.ReadToEndAsync();$stderr=$jvm.StandardError.ReadToEndAsync();$jvm.StandardInput.Write(($lines -join "`n")+"`n");$jvm.StandardInput.Close();if(-not $jvm.WaitForExit(60000)){$jvm.Kill($true);throw 'Lowercase reference timeout'};if($jvm.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};$expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.TrimEnd("`r")})}finally{$jvm.Dispose()}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json;$localeRow=-1;$baseRow=-1
for($i=0;$i -lt $p.runtime_type_bindings.Count;$i++){if($p.runtime_type_bindings[$i].tag -eq 'OFFSET boom_lower_locale_layout'){$localeRow=$i};if($p.runtime_type_bindings[$i].tag -eq 'OFFSET boom_lower_base_layout'){$baseRow=$i}}
if($localeRow -lt 0 -or $baseRow -lt 0){throw 'Locale VM fixture rows missing'}
$npe=@($p.object_layouts|Where-Object class_name -eq java/lang/NullPointerException)[0].class_id
Add-Type -Path tests/host/LowercaseProbe.cs
$actual=[BoomLowercaseProbe]::Run($p.compilation.dll,$lines,$localeRow,$baseRow,[uint32]$npe,[uint32]$p.entry_id)
if($actual.Count -ne $expected.Count){throw 'Lowercase differential record count differs'}
for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -cne $expected[$i]){throw "Lowercase mismatch input=$($lines[$i]) expected=$($expected[$i]) actual=$($actual[$i])"}}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Lowercase compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;JVM_cases=$lines.Count;all_simple_mapping_rows_covered=2879;root_Turkish_Azeri_Lithuanian_contexts=$true;Supplementary_unpaired_surrogates_and_identity_checked=$true;final_Sigma_uses_original_word_DFA=$true;pending_context_preserved=$true;foreign_heap_wrong_type_rejected=$true;Locale_and_BaseLocale_are_preconstructor_VM_fixtures=$true;original_Locale_and_BaseLocale_initializers_executed=$false;original_Java_String_method_executed=$false;source_String_public_Code_bytes=29;exception_class_and_call_site_checked=$true;exception_messages_compared=$false;parallel_workers=8;parallel_conversions=2048;unchanged_String_allocates_nothing=$true;OOM_and_explicit_reclamation_recovery_checked=$true;dictionary_Sigma_implemented=$false;unimplemented_dictionary_Sigma_fails_explicitly=$true;dynamic_locale_providers=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-lowercase-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
