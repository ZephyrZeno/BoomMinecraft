// Runs original Finalizer.<clinit>/getQueue and original queue constructors in ASM.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomFinalizerProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint id,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Contains(IntPtr h,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool b,string s) { if(!b)throw new Exception(s); }
    static T Fn<T>(IntPtr m,string n) { IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    public static void Run(string dll,string runtime,uint finalizer,uint enabled,uint queue,uint gate,uint unfinalized,uint queueClass) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Finalizer image load");
        try {
            heap=Fn<Create>(r,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Finalizer heap binding");
            var entry=Fn<Entry>(m,GetProcAddress(m,"boom_entry32")!=IntPtr.Zero?"boom_entry32":"boom_entry"); var field=Fn<Field>(m,"boom_get_static_field");
            var results=new ulong[1024];
            Parallel.For(0,8,worker=> {for(int i=0;i<128;i++) {var c=new Context();ulong value=entry(ref c,IntPtr.Zero);Check(c.Kind==0&&c.Depth==0&&value!=0,"Original Finalizer Java execution failed: "+c.Kind+" method "+c.Method+" pc "+c.PC);results[worker*128+i]=value;}});
            foreach(ulong result in results)Check(result==results[0],"Finalizer queues lost canonical identity");
            IntPtr valuePtr=new IntPtr(unchecked((long)results[0]));
            Check(Marshal.ReadInt64(field(finalizer,enabled))==0,"Finalization-disabled policy not published by original Java");
            Check(Marshal.ReadIntPtr(field(finalizer,queue))==valuePtr&&Marshal.ReadIntPtr(field(finalizer,gate))!=IntPtr.Zero&&Marshal.ReadIntPtr(field(finalizer,unfinalized))==IntPtr.Zero,"Original Finalizer static graph differs");
            Check(Marshal.ReadIntPtr(valuePtr,-8)==Fn<Indexed>(m,"boom_get_object_layout")(queueClass),"Original NativeReferenceQueue constructor did not execute");
            Check(Marshal.ReadInt32(Fn<Indexed>(m,"boom_get_class_descriptor")(finalizer),8)==2,"Finalizer Java initialization did not complete");
            if(GetProcAddress(m,"boom_release_trace_pool")!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Finalizer Java frames remained active");
            IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint count);
            Fn<Collect>(r,"boom_heap_collect")(heap,roots,count);
            Check(Fn<Contains>(r,"boom_heap_contains")(heap,valuePtr)==1,"Finalizer queue was missing from GC roots");
            var after=new Context();Check(entry(ref after,IntPtr.Zero)==results[0]&&after.Kind==0,"Finalizer graph changed after quiescent collection");
        } finally {
            if(m!=IntPtr.Zero&&GetProcAddress(m,"boom_release_trace_pool")!=IntPtr.Zero)Fn<Release>(m,"boom_release_trace_pool")();
            if(heap!=IntPtr.Zero)Fn<Bind>(r,"boom_heap_destroy")(heap);
            if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);
        }
    }
}
