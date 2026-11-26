// Development host only. Registration, UTC arithmetic, Java bodies and GC are MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomVmRegistrationProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr zero,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [DllImport("kernel32.dll")] static extern void GetSystemTimePreciseAsFileTime(out ulong time);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Get();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(ref Context c,[In] ulong[] args,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Arithmetic(ulong ft,long offset);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static IntPtr Open(string path){IntPtr m=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"VM module load failed");return m;}
    static T Fn<T>(IntPtr m,string name){IntPtr p=GetProcAddress(m,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static void GC(IntPtr m,IntPtr h){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(h,roots,n)!=ulong.MaxValue,"VM static roots collection failed");}
    static long Expected(ulong ft,long offset){decimal ticks=ft,seconds=decimal.Floor(ticks/10000000m),nanos=(ticks-seconds*10000000m)*100m;decimal diff=seconds-11644473600m-offset;return diff>=4294967296m||diff<=-4294967296m?-1:(long)(diff*1000000000m+nanos);}
    public static ulong NowFileTime(){GetSystemTimePreciseAsFileTime(out ulong ft);return ft;}
    public static void ReferenceClock(string[] values,ulong before,ulong after){long lo=Expected(before,0),hi=Expected(after,0);foreach(string line in values){Check(line.StartsWith("v "),"Malformed JVM UTC record");long value=unchecked((long)Convert.ToUInt64(line.Substring(2),16));Check(value>=Math.Min(lo,hi)&&value<=Math.Max(lo,hi),"JVM UTC result outside Win32 bracket");}}
    public static int ArithmeticCases(string dll){IntPtr m=Open(dll);int count=0;try{
        var f=Fn<Arithmetic>(m,"boom_vm_adjustment_from_filetime");
        foreach(ulong time in new ulong[]{0,1,9999999,10000000,116444735999999999,116444736000000000,116444736000000001,116444736009999999,ulong.MaxValue}){
            long seconds=(long)(time/10000000)-11644473600L;
            foreach(long delta in new long[]{-4294967297L,-4294967296L,-4294967295L,-1,0,1,4294967295L,4294967296L,4294967297L}){long offset=seconds-delta;Check(f(time,offset)==Expected(time,offset),"VM boundary arithmetic mismatch");count++;}
            foreach(long offset in new long[]{long.MinValue,long.MaxValue,0,-1,1}){Check(f(time,offset)==Expected(time,offset),"VM extreme arithmetic mismatch");count++;}
        }
        var random=new Random(43043);byte[] bytes=new byte[8];
        for(int i=0;i<20000;i++){random.NextBytes(bytes);ulong time=BitConverter.ToUInt64(bytes,0);random.NextBytes(bytes);long offset=BitConverter.ToInt64(bytes,0);if((i&1)==0)offset=(long)(time/10000000)-11644473600L+(offset%4294967299L);Check(f(time,offset)==Expected(time,offset),"VM random arithmetic mismatch");count++;}
        return count;
    }finally{Check(FreeLibrary(m),"Arithmetic module cleanup failed");}}
    public static void Native(string dll){IntPtr m=Open(dll),h=IntPtr.Zero;try{
        h=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(h!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(h)==1,"VM heap setup failed");
        IntPtr pool=Fn<Get>(m,"boom_get_vm_native_pool")();var service=Fn<Service>(m,"boom_vm_native");var entry=Fn<Entry>(m,"boom_entry");
        Check(Marshal.ReadInt32(pool,8)==0&&Marshal.ReadInt64(h,56)==0,"VM registration did not start cold");
        var c=new Context();Check(service(ref c,new ulong[]{0},pool,1)==0&&c.Kind==7&&Marshal.ReadInt32(pool,8)==0,"Unregistered VM target accepted");
        c=new Context();Check(entry(ref c,new ulong[]{0})==0&&c.Kind==0&&c.Depth==0&&Marshal.ReadInt32(pool,8)==2,"Original VM initializer/state body did not register without booting");
        GC(m,h);long baseline=Marshal.ReadInt64(h,56);Check(baseline>=1,"Original VM lock allocation missing");
        for(int i=0;i<8193;i++){c=new Context();Check(service(ref c,null,pool,0)==0&&c.Kind==0&&Marshal.ReadInt32(pool,8)==2&&Marshal.ReadInt64(h,56)==baseline,"Repeated VM registration changed heap/state");}
        for(int i=0;i<512;i++){GetSystemTimePreciseAsFileTime(out ulong before);long offset=(i&1)==0?0:(long)(before/10000000)-11644473600L;c=new Context();long actual=unchecked((long)service(ref c,new ulong[]{unchecked((ulong)offset)},pool,1));GetSystemTimePreciseAsFileTime(out ulong after);long lo=Expected(before,offset),hi=Expected(after,offset);Check(c.Kind==0&&actual>=Math.Min(lo,hi)&&actual<=Math.Max(lo,hi)&&Marshal.ReadInt64(h,56)==baseline,"VM live UTC result outside Win32 clock bracket");}
        c=new Context{Kind=9,PC=17,Method=23,Depth=3};Check(service(ref c,null,IntPtr.Zero,0)==0&&c.Kind==9&&c.PC==17&&c.Method==23&&c.Depth==3,"VM registration changed pending context");
        IntPtr bad=Marshal.AllocHGlobal(32);try{byte[] data=new byte[32];Marshal.Copy(pool,data,0,32);foreach(int offset in new int[]{0,4,8,12,16,24}){Marshal.Copy(data,0,bad,32);if(offset<16)Marshal.WriteInt32(bad,offset,offset==8?1:7);else Marshal.WriteIntPtr(bad,offset,new IntPtr(1));c=new Context{PC=17,Method=23};Check(service(ref c,new ulong[]{0},bad,1)==0&&c.Kind==7&&c.PC==17&&c.Method==23,"VM accepted malformed registration metadata");}
            c=new Context();Check(service(ref c,null,pool,2)==0&&c.Kind==7,"Unknown VM operation accepted");c=new Context();Check(service(ref c,null,pool,1)==0&&c.Kind==7,"VM accepted absent arguments");
        }finally{Marshal.FreeHGlobal(bad);}
        Check(Marshal.ReadInt64(h,56)==baseline,"VM metadata gates allocated");GC(m,h);c=new Context();Check(entry(ref c,new ulong[]{0})==0&&c.Kind==0&&Marshal.ReadInt64(h,56)==baseline,"VM lock/state lost after GC");
    }finally{IntPtr p=GetProcAddress(m,"boom_release_trace_pool");if(p!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"VM Java frames active at cleanup");if(h!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(h)!=0,"VM heap cleanup failed");Check(FreeLibrary(m),"VM module cleanup failed");}}
    public static void Adjustment(string dll){IntPtr m=Open(dll),h=IntPtr.Zero;try{h=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(h!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(h)==1,"VM adjustment setup failed");var entry=Fn<Entry>(m,"boom_entry");
        for(int i=0;i<512;i++){GetSystemTimePreciseAsFileTime(out ulong before);long offset=i%3==0?long.MinValue:i%3==1?long.MaxValue:(long)(before/10000000)-11644473600L;var c=new Context();long actual=unchecked((long)entry(ref c,new ulong[]{unchecked((ulong)offset)}));GetSystemTimePreciseAsFileTime(out ulong after);long lo=Expected(before,offset),hi=Expected(after,offset);Check(c.Kind==0&&actual>=Math.Min(lo,hi)&&actual<=Math.Max(lo,hi),"Original VM adjustment call/initializer mismatch");GC(m,h);}
    }finally{if(h!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(h)!=0,"Adjustment cleanup failed");Check(FreeLibrary(m),"Adjustment module cleanup failed");}}
}
