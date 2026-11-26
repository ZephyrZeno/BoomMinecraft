// Managed code only controls rounds. All stores, full fences, loads and resets
// in the measured litmus are original Java bytecode translated into AOT ASM.
using System;
using System.Runtime.InteropServices;
using System.Threading;
public static class BoomFenceProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth;public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string path,IntPtr zero,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr image,string name);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr image);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Entry(ref Context c,[In]ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    static void Check(bool value,string message) { if(!value)throw new Exception(message); }
    static T Fn<T>(IntPtr image,string name) { IntPtr p=GetProcAddress(image,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static int Invoke(Entry entry,ulong[] args) { var c=new Context();ulong value=entry(ref c,args);Check(c.Kind==0&&c.Depth==0,"Fence Java caller failed: kind="+c.Kind+" method="+c.Method+" pc="+c.PC);return unchecked((int)value); }
    public static void Run(string dll,string runtime,int rounds) {
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"Fence image load failed");
        try {
            heap=Fn<Create>(rt,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(image,"boom_bind_heap")(heap)==1,"Fence heap bind failed");
            var entry=Fn<Entry>(image,GetProcAddress(image,"boom_entry32")!=IntPtr.Zero?"boom_entry32":"boom_entry");
            ulong[] reset={2};Invoke(entry,reset);Invoke(entry,new[]{0UL});Invoke(entry,new[]{1UL});Invoke(entry,reset);
            long before=Marshal.ReadInt64(heap,48);var cancel=new CancellationTokenSource();var barrier=new Barrier(3);int[] results=new int[2];Exception[] failures=new Exception[2];Thread[] workers=new Thread[2];
            try {
                for(int slot=0;slot<2;slot++) { int index=slot;workers[index]=new Thread(()=>{try{ulong[] args={(ulong)index};for(int i=0;i<rounds;i++){barrier.SignalAndWait(cancel.Token);results[index]=Invoke(entry,args);barrier.SignalAndWait(cancel.Token);}}catch(Exception error){failures[index]=error;cancel.Cancel();}});workers[index].IsBackground=true;workers[index].Start(); }
                for(int i=0;i<rounds;i++) { Invoke(entry,reset);barrier.SignalAndWait(cancel.Token);barrier.SignalAndWait(cancel.Token);Check((results[0]|results[1])!=0,"Forbidden store/load outcome at round "+i); }
            } finally { cancel.Cancel();foreach(Thread worker in workers)if(worker!=null)Check(worker.Join(10000),"Fence worker did not finish");barrier.Dispose();cancel.Dispose(); }
            foreach(Exception error in failures)if(error!=null)throw error;
            Check(Marshal.ReadInt64(heap,48)==before,"Warm fence litmus allocated guest objects");
        } finally { if(image!=IntPtr.Zero&&GetProcAddress(image,"boom_release_trace_pool")!=IntPtr.Zero)Check(Fn<Release>(image,"boom_release_trace_pool")()==0,"Fence frames remain");if(heap!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(heap);if(rt!=IntPtr.Zero)FreeLibrary(rt);if(image!=IntPtr.Zero)FreeLibrary(image); }
    }
}
