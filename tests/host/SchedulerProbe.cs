// Diagnostic host only. Scheduling, profiling and execution are assembly.
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
public static class BoomSchedulerProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Reserved; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(uint jobs);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Run(IntPtr state,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Budget(IntPtr state);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Action(IntPtr state);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint RunBudget(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count,uint jobs);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong budget);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong HeapCollect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {
        IntPtr symbol=GetProcAddress(module,name);if(symbol==IntPtr.Zero)throw new Exception("Missing "+name);
        return Marshal.GetDelegateForFunctionPointer<T>(symbol);
    }
    public sealed class Sample { public int run,jobs;public double elapsed_ms,gc_ms; }
    public sealed class Measurement {public string method;public int records,executions,chosen_jobs;public Sample[] samples;}
    public static Measurement Measure(string runtime,string dll,string method,int count,bool useHeap) {
        IntPtr library=IntPtr.Zero,module=IntPtr.Zero,state=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero,heap=IntPtr.Zero;
        Action destroy=null;HeapDestroy destroyHeap=null;HeapCollect collect=null;
        try {
            library=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);
            if(library==IntPtr.Zero||module==IntPtr.Zero)throw new Exception("Scheduler module load failed");
            var create=Symbol<Create>(library,"boom_scheduler_create");destroy=Symbol<Action>(library,"boom_scheduler_destroy");
            var run=Symbol<Run>(library,"boom_scheduler_run");var budget=Symbol<Budget>(library,"boom_scheduler_budget");
            var entry=Symbol<Entry>(module,"boom_entry");IntPtr kernel=GetProcAddress(module,"boom_entry");
            if(useHeap) {
                var make=Symbol<HeapCreate>(module,"boom_heap_create");destroyHeap=Symbol<HeapDestroy>(module,"boom_heap_destroy");
                collect=Symbol<HeapCollect>(module,"boom_heap_collect");var bind=Symbol<Bind>(module,"boom_bind_heap");
                heap=make(64*1024*1024);if(heap==IntPtr.Zero||bind(heap)!=1)throw new Exception("Scheduler test heap setup failed");
            }
            var values=new long[count*16];var expected=new long[count*4];var actual=new long[expected.Length];var args=new ulong[16];
            for(int i=0;i<count;i++) {
                if(method=="longLoop") {args[0]=unchecked((ulong)i*0x123456789abcdefUL);args[1]=512;}
                else if(method=="intObject") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=unchecked((uint)(i*37));}
                else if(method=="linkedObjects") {args[0]=(uint)(i%33);args[1]=unchecked((uint)(i*1664525+1013904223));}
                else if(method=="pair"||method=="wide") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=unchecked((uint)(i*37));}
                else if(method=="graph") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=(uint)(i%17);}
                else if(method=="arrays") {int n=i%17;args[0]=(uint)n;args[1]=unchecked((uint)(n==0||i%7==0?n:i%n));}
                else if(method=="nullField") {args[0]=unchecked((uint)(i%37==0?-1:i));}
                else throw new Exception("Unknown scheduler fixture");
                for(int a=0;a<16;a++)values[i*16+a]=unchecked((long)args[a]);
                var context=new Context();expected[i*4]=unchecked((long)entry(ref context,args));
                expected[i*4+1]=unchecked((long)((ulong)context.Kind|((ulong)context.PC<<32)));
                expected[i*4+2]=unchecked((long)((ulong)context.Method|((ulong)context.Reserved<<32)));
            }
            if(useHeap&&collect(heap,IntPtr.Zero,0)==ulong.MaxValue)throw new Exception("Baseline GC failed");
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            state=create(8);if(state==IntPtr.Zero)throw new Exception("Scheduler create failed");
            var samples=new Sample[12];uint chosen=0;
            for(int repeat=0;repeat<samples.Length;repeat++) {
                for(int i=0;i<actual.Length;i++)actual[i]=unchecked((long)0xccccccccccccccccUL);
                Marshal.Copy(actual,0,output,actual.Length);var watch=Stopwatch.StartNew();
                uint error=run(state,kernel,input,output,(uint)count);watch.Stop();if(error!=0)throw new Exception("Scheduler run failed: "+error);
                uint active=budget(state);if(active<1||active>8)throw new Exception("Invalid active worker count");
                if(repeat<8&&active!=(1u<<(repeat/2)))throw new Exception("Candidate budget order differs");
                if(repeat==8)chosen=active;if(repeat>8&&active!=chosen)throw new Exception("Selected budget was unstable");
                Marshal.Copy(output,actual,0,actual.Length);
                for(int i=0;i<actual.Length;i++)if(actual[i]!=expected[i])throw new Exception(method+" scheduler mismatch record "+i/4+" field "+i%4);
                var gc=Stopwatch.StartNew();if(useHeap&&(collect(heap,IntPtr.Zero,0)==ulong.MaxValue||Marshal.ReadInt64(heap,48)!=0))throw new Exception("Batch GC failed");gc.Stop();
                samples[repeat]=new Sample{run=repeat,jobs=(int)active,elapsed_ms=watch.Elapsed.TotalMilliseconds,gc_ms=useHeap?gc.Elapsed.TotalMilliseconds:0};
            }
            return new Measurement{method=method,records=count,executions=count*12,chosen_jobs=(int)chosen,samples=samples};
        }finally {
            if(state!=IntPtr.Zero&&destroy!=null)destroy(state);if(heap!=IntPtr.Zero&&destroyHeap!=null)destroyHeap(heap);
            if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);
            if(module!=IntPtr.Zero)FreeLibrary(module);if(library!=IntPtr.Zero)FreeLibrary(library);
        }
    }
    public static void CheckPolicies(string runtime,string probePath) {
        IntPtr library=IntPtr.Zero,probe=IntPtr.Zero,state=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero,counter=IntPtr.Zero,pool=IntPtr.Zero;
        Action destroy=null,destroyPool=null;Thread thread=null;
        try {
            library=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);probe=LoadLibraryExW(probePath,IntPtr.Zero,0x1100);
            if(library==IntPtr.Zero||probe==IntPtr.Zero)throw new Exception("Policy module load failed");
            var create=Symbol<Create>(library,"boom_scheduler_create");destroy=Symbol<Action>(library,"boom_scheduler_destroy");
            var run=Symbol<Run>(library,"boom_scheduler_run");var budget=Symbol<Budget>(library,"boom_scheduler_budget");var reset=Symbol<Action>(library,"boom_scheduler_reset");
            if(create(0)!=IntPtr.Zero||create(65)!=IntPtr.Zero||destroy(IntPtr.Zero)!=87||reset(IntPtr.Zero)!=87||budget(IntPtr.Zero)!=0||run(IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,1)!=87)throw new Exception("Invalid scheduler arguments accepted");
            const int count=1027;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);counter=Marshal.AllocHGlobal(8);Marshal.WriteInt64(counter,0);
            var values=new long[count*16];for(int i=0;i<count;i++){values[i*16]=counter.ToInt64();values[i*16+1]=i;}
            Marshal.Copy(values,0,input,values.Length);IntPtr counted=GetProcAddress(probe,"boom_probe_counted"),gate=GetProcAddress(probe,"boom_probe_gate");
            state=create(8);if(state==IntPtr.Zero)throw new Exception("Policy scheduler create failed");
            if(run(state,counted,input,input,count)!=87||run(state,IntPtr.Zero,input,output,count)!=87)throw new Exception("Invalid scheduler buffers accepted");
            if(Marshal.ReadInt32(state,32)!=0)throw new Exception("Failed run consumed tuning sample");
            if(run(state,counted,input,output,0)!=0||Marshal.ReadInt64(counter)!=0||Marshal.ReadInt32(state,32)!=0)throw new Exception("Empty run executed/tuned work");
            var actual=new long[count*4];
            for(int repeat=0;repeat<12;repeat++) {
                if(run(state,counted,input,output,count)!=0)throw new Exception("Counted scheduler run failed");
                if(Marshal.ReadInt64(counter)!=(long)(repeat+1)*count)throw new Exception("Scheduler replayed or lost records");
                Marshal.Copy(output,actual,0,actual.Length);
                for(int i=0;i<count;i++)if(actual[i*4]!=i||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Counted outputs invalid");
            }
            Marshal.WriteInt64(counter,1);
            if(run(state,gate,input,output,count)!=0||budget(state)!=1||Marshal.ReadInt32(state,32)!=1)throw new Exception("Changing a trained kernel did not restart profiling");
            if(run(state,counted,input,output,count)!=0||budget(state)!=1||Marshal.ReadInt32(state,32)!=1)throw new Exception("Changing back to the original kernel reused stale profiling");
            if(reset(state)!=0||budget(state)!=1)throw new Exception("Explicit reset failed");
            if(run(state,counted,input,output,13)!=0||budget(state)!=1||Marshal.ReadInt32(state,32)!=0)throw new Exception("Small batch should remain serial without training");
            // A different kernel must reset tuning, and an active call blocks reset/run/destroy.
            Marshal.WriteInt64(counter,0);uint result=999;Exception failure=null;
            thread=new Thread(()=>{try{result=run(state,gate,input,output,count);}catch(Exception error){failure=error;}});thread.Start();
            var watch=Stopwatch.StartNew();while(Marshal.ReadInt32(state,4)==0&&watch.ElapsedMilliseconds<5000)Thread.Yield();
            if(Marshal.ReadInt32(state,4)!=1||reset(state)!=170||destroy(state)!=170||run(state,gate,input,output,count)!=170)throw new Exception("Busy scheduler lifecycle not protected");
            Marshal.WriteInt64(counter,1);if(!thread.Join(10000))throw new Exception("Gate did not finish");if(failure!=null)throw failure;if(result!=0||budget(state)!=1)throw new Exception("Kernel transition failed");
            if(destroy(state)!=0)throw new Exception("Scheduler destruction failed");state=IntPtr.Zero;
            var createPool=Symbol<Create>(library,"boom_pool_create");destroyPool=Symbol<Action>(library,"boom_pool_destroy");var runBudget=Symbol<RunBudget>(library,"boom_pool_run_budget");
            pool=createPool(8);if(pool==IntPtr.Zero)throw new Exception("Budget pool create failed");
            if(runBudget(pool,counted,input,output,count,0)!=87||runBudget(pool,counted,input,output,count,65)!=87)throw new Exception("Invalid explicit budget accepted");
            foreach(uint active in new uint[]{8,1,4,2,1,8}) {
                Marshal.WriteInt64(counter,0);if(runBudget(pool,counted,input,output,count,active)!=0||Marshal.ReadInt64(counter)!=count)throw new Exception("Explicit budget lost work");
            }
            if(destroyPool(pool)!=0)throw new Exception("Budget pool destruction failed");pool=IntPtr.Zero;
        }finally {
            if(thread!=null&&thread.IsAlive){if(counter!=IntPtr.Zero)Marshal.WriteInt64(counter,1);thread.Join();}
            if(state!=IntPtr.Zero&&destroy!=null)destroy(state);if(pool!=IntPtr.Zero&&destroyPool!=null)destroyPool(pool);
            if(counter!=IntPtr.Zero)Marshal.FreeHGlobal(counter);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);
            if(probe!=IntPtr.Zero)FreeLibrary(probe);if(library!=IntPtr.Zero)FreeLibrary(library);
        }
    }
}
