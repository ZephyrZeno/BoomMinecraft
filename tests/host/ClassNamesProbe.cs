// Runs original caller bytecode through the AOT Object/Member dispatch tables.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomClassNamesProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In]ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pool();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Name(ref Context c,[In]ulong[] argv,IntPtr pool,uint operation);
    static void Check(bool value,string message) { if(!value) throw new Exception(message); }
    static T Fn<T>(IntPtr image,string name) { IntPtr p=GetProcAddress(image,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static string Invoke(Entry entry,uint mode) {
        var c=new Context();ulong value=entry(ref c,new[]{(ulong)mode});Check(c.Kind==0&&c.Depth==0&&value!=0,"Reflection virtual call failed mode="+mode+" kind="+c.Kind+" method="+c.Method+" pc="+c.PC);
        IntPtr text=new IntPtr(unchecked((long)value));Check(Marshal.ReadInt64(text,-16)==16&&Marshal.ReadInt32(text,-20)==1,"Reflection result is not a VM String");
        IntPtr chars=Marshal.ReadIntPtr(text);Check(Marshal.ReadIntPtr(chars,-8).ToInt64()==261,"Reflection result lacks UTF16 data");
        return Marshal.PtrToStringUni(chars,checked((int)(Marshal.ReadInt64(chars,-16)/2)));
    }
    public static string[] Run(string dll,string runtime) {
        return RunCases(dll,runtime,12);
    }
    public static string[] RunCases(string dll,string runtime,uint modes) {
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"Reflection dispatch image load failed");
        try {
            heap=Fn<Create>(rt,"boom_heap_create")(67108864);Check(heap!=IntPtr.Zero&&Fn<One>(image,"boom_bind_heap")(heap)==1,"Reflection dispatch heap bind failed");
            var entry=Fn<Entry>(image,GetProcAddress(image,"boom_entry32")!=IntPtr.Zero?"boom_entry32":"boom_entry");string[] expected=new string[modes];for(uint mode=0;mode<modes;mode++) expected[mode]=Invoke(entry,mode);
            Parallel.For(0,8,worker=>{for(int i=0;i<256;i++){uint mode=(uint)i%modes;Check(Invoke(entry,mode)==expected[mode],"Concurrent reflection dispatch differs");}});
            IntPtr pool=Fn<Pool>(image,"boom_get_class_name_pool")();
            Check(Marshal.ReadInt32(pool,4)==2,"Class name cache ABI differs");
            int count=Marshal.ReadInt32(pool,8)*2;IntPtr cache=Marshal.ReadIntPtr(pool,40),locks=Marshal.ReadIntPtr(pool,48);long[] saved=new long[count];
            for(int i=0;i<count;i++){saved[i]=Marshal.ReadInt64(cache,i*8);Check(Marshal.ReadInt32(locks,i*4)==0,"Class name cache lock remained held");}
            IntPtr roots=Fn<Roots>(image,"boom_get_static_roots")(out uint rootCount);
            Check(Fn<Collect>(rt,"boom_heap_collect")(heap,roots,rootCount)!=ulong.MaxValue,"Class name cache static roots were not collectable");
            for(int i=0;i<count;i++)Check(saved[i]==Marshal.ReadInt64(cache,i*8),"Class name cache identity changed after collection");
            for(uint mode=0;mode<modes;mode++)Check(Invoke(entry,mode)==expected[mode],"Class name result changed after collection");
            long before=Marshal.ReadInt64(heap,48);var name=Fn<Name>(rt,"boom_class_name");IntPtr mirrors=Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,16),16);
            Parallel.For(0,8,worker=>{for(int round=0;round<16;round++)for(int i=0;i<count;i++)if(saved[i]!=0){var c=new Context();ulong value=name(ref c,new[]{unchecked((ulong)Marshal.ReadInt64(mirrors,(i/2)*8))},pool,(uint)(i%2));Check(c.Kind==0&&value==unchecked((ulong)saved[i]),"Hot cached class name identity differs");}});
            Check(Marshal.ReadInt64(heap,48)==before,"Hot cached name queries allocated guest objects");
            return expected;
        } finally { if(image!=IntPtr.Zero&&GetProcAddress(image,"boom_release_trace_pool")!=IntPtr.Zero)Check(Fn<Release>(image,"boom_release_trace_pool")()==0,"Reflection dispatch frames remain");if(heap!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(heap);if(rt!=IntPtr.Zero)FreeLibrary(rt);if(image!=IntPtr.Zero)FreeLibrary(image); }
    }
}
