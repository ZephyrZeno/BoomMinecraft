// Child-only execution for the real terminating Java path. No desktop control.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomShutdownProbe {
    [StructLayout(LayoutKind.Sequential)]struct Context { public uint Kind,PC,Method,Depth;public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Entry(ref Context c,[In]ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Native(ref Context c,[In]ulong[] args,IntPtr pool,uint op);
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static void HaltInOwnedChild(string dll,string runtime,int code){
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"Shutdown child images failed to load");IntPtr heap=Fn<Create>(rt,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(image,"boom_bind_heap")(heap)==1,"Shutdown child heap bind failed");var c=new Context();Fn<Entry>(image,"boom_entry32")(ref c,new[]{unchecked((ulong)(uint)code)});throw new Exception("Original Shutdown.halt returned kind="+c.Kind+" method="+c.Method+" pc="+c.PC);
    }
    public static void EventChecks(string dll,string runtime){
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"Shutdown event images failed to load");
        try {
            heap=Fn<Create>(rt,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero,"Shutdown event heap failed");IntPtr pool=Fn<Pointer>(image,"boom_get_shutdown_pool")();var native=Fn<Native>(rt,"boom_shutdown_native");long start=Marshal.ReadInt64(pool,8),used=Marshal.ReadInt64(heap,48);
            Parallel.For(0,8,worker=>{for(int i=0;i<1024;i++){var c=new Context();Check(native(ref c,null,pool,0)==0&&c.Kind==0,"Shutdown event failed");}});Check(Marshal.ReadInt64(pool,8)==start+8192&&Marshal.ReadInt32(pool,20)==0&&Marshal.ReadInt64(heap,48)==used,"Shutdown event count, termination state or guest allocation differs");
            var pending=new Context{Kind=5,PC=17,Method=13,Pending=123};native(ref pending,new[]{1UL},pool,1);Check(pending.Kind==5&&pending.PC==17&&pending.Method==13&&pending.Pending==123&&Marshal.ReadInt32(pool,20)==0,"Pending halt request changed state");
            var missing=new Context();Check(native(ref missing,null,pool,1)==0&&missing.Kind==7,"Halt accepted missing status arguments");var invalid=new Context();Check(native(ref invalid,null,pool,2)==0&&invalid.Kind==7,"Invalid shutdown operation accepted");
            IntPtr malformed=Marshal.AllocHGlobal(32);try {for(int i=0;i<4;i++)Marshal.WriteInt64(malformed,i*8,Marshal.ReadInt64(pool,i*8));Marshal.WriteInt32(malformed,4,0);var c=new Context();Check(native(ref c,new[]{1UL},malformed,1)==0&&c.Kind==7&&Marshal.ReadInt32(pool,20)==0,"Malformed halt metadata was accepted");}finally{Marshal.FreeHGlobal(malformed);}
        } finally {if(heap!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(heap);if(rt!=IntPtr.Zero)FreeLibrary(rt);if(image!=IntPtr.Zero)FreeLibrary(image);}
    }
}
