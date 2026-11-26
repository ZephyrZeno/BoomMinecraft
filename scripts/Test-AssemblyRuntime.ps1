param([string]$Boom='target\release\boom.exe',[int]$Count=65539)
$ErrorActionPreference='Stop'
if ($Count -lt 1024 -or $Count -gt 1000000) { throw 'Test count must be 1024..1000000.' }
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw | ConvertFrom-Json
$root=Join-Path $projectRoot ('.boom\runtime-tests\'+[guid]::NewGuid().ToString('N'))
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
$classes=Join-Path $root 'classes'
[IO.Directory]::CreateDirectory($classes) | Out-Null
$javac=Join-Path (Split-Path -Parent $tools.java) 'javac.exe'
& $javac --release 21 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\IntKernels.java')
if ($LASTEXITCODE -ne 0) { throw 'javac failed.' }
$kernelOutput=Join-Path $root 'kernel'
& $boomPath compile-asm --class-file (Join-Path $classes 'dev\boom\subset\IntKernels.class') --method parallelWork --output $kernelOutput --assemble | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Own assembly compiler failed.' }

# This C# code is only a disposable measurement host. All tested work and
# scheduling execute in the two assembly DLLs, never inside this host or a JVM.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Diagnostics;
public static class BoomAssemblyProbe {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr LoadLibraryExW(string file, IntPtr reserved, uint flags);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Map(IntPtr kernel, IntPtr input, IntPtr output, uint count, uint jobs);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Kernel(int a, int b, int c, int d);
    public sealed class Measurement { public int jobs; public double elapsed_ms; public int cases; public bool passed; }
    public static Measurement[] Run(string runtime, string kernelPath, int count) {
        IntPtr library=IntPtr.Zero, code=IntPtr.Zero, input=IntPtr.Zero, output=IntPtr.Zero;
        try {
            library=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);
            code=LoadLibraryExW(kernelPath,IntPtr.Zero,0x1100);
            if (library==IntPtr.Zero || code==IntPtr.Zero) throw new Exception("Cannot load assembly DLLs: "+Marshal.GetLastWin32Error());
            IntPtr symbol=GetProcAddress(code,"boom_entry");
            IntPtr mapSymbol=GetProcAddress(library,"boom_parallel_i32");
            if (symbol==IntPtr.Zero || mapSymbol==IntPtr.Zero) throw new Exception("Missing export");
            Kernel kernel=Marshal.GetDelegateForFunctionPointer<Kernel>(symbol);
            Map map=Marshal.GetDelegateForFunctionPointer<Map>(mapSymbol);
            int[] values=new int[checked(count*4)], expected=new int[count], actual=new int[count];
            for(int i=0;i<count;i++) {
                int a=unchecked(i*1664525+1013904223);
                values[i*4]=a; values[i*4+1]=1013904223; values[i*4+2]=255; values[i*4+3]=1024;
                expected[i]=kernel(a,1013904223,255,1024);
            }
            input=Marshal.AllocHGlobal(checked(count*16)); output=Marshal.AllocHGlobal(checked(count*4));
            Marshal.Copy(values,0,input,values.Length);
            if(map(symbol,input,output,(uint)count,0)!=87 || map(symbol,input,output,(uint)count,65)!=87) throw new Exception("Invalid worker budgets accepted");
            if(map(symbol,input,input,(uint)count,4)!=87) throw new Exception("Aliasing buffers accepted");
            if(map(IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,0,4)!=0) throw new Exception("Empty map failed");
            if(map(symbol,input,output,16777217,4)!=87) throw new Exception("Oversized count accepted");
            var results=new Measurement[4]; int[] budgets={1,2,4,8};
            map(symbol,input,output,1024,1); // Warm instruction pages before measurement.
            for(int b=0;b<budgets.Length;b++) {
                var watch=Stopwatch.StartNew();
                uint error=map(symbol,input,output,(uint)count,(uint)budgets[b]);
                watch.Stop();
                if(error!=0) throw new Exception("Runtime returned "+error);
                Marshal.Copy(output,actual,0,count);
                for(int i=0;i<count;i++) if(actual[i]!=expected[i]) throw new Exception("Mismatch at "+i+" with "+budgets[b]+" jobs");
                results[b]=new Measurement {jobs=budgets[b],elapsed_ms=watch.Elapsed.TotalMilliseconds,cases=count,passed=true};
            }
            // Repeated calls detect stale counters and stack/context lifetime mistakes.
            for(int run=0;run<20;run++) {
                if(map(symbol,input,output,(uint)(run+1),4)!=0) throw new Exception("Short map failed");
                Marshal.Copy(output,actual,0,run+1);
                for(int i=0;i<=run;i++) if(actual[i]!=expected[i]) throw new Exception("Repeated map mismatch");
            }
            return results;
        } finally {
            if(input!=IntPtr.Zero) Marshal.FreeHGlobal(input);
            if(output!=IntPtr.Zero) Marshal.FreeHGlobal(output);
            if(code!=IntPtr.Zero) FreeLibrary(code);
            if(library!=IntPtr.Zero) FreeLibrary(library);
        }
    }
}
'@
$measurements=[BoomAssemblyProbe]::Run((Join-Path $root 'boom-runtime.dll'),(Join-Path $kernelOutput 'method.dll'),$Count)
$report=[ordered]@{ implementation_language='assembly'; kernel_backend='boom-i32-v2-masm-x64'; count=$Count; measurements=$measurements; scheduler='bounded workers, atomic 64-record chunks, ordered outputs, caller participation'; argument_and_alias_checks=$true; repeated_calls=20; passed=$true; game_integration_complete=$false; run_directory=$root }
$json=$report | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
Write-Output $json
