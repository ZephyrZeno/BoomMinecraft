// Controller only. Java wrappers, field lookup, actual-class maps and atomics
// execute in the generated ASM image or the ASM runtime.
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
public static class BoomObjectFieldsProbe {
    [StructLayout(LayoutKind.Sequential)]struct Context { public uint Kind,PC,Method,Depth;public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Entry(ref Context c,[In]ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    static void Check(bool value,string message) { if(!value)throw new Exception(message); }
    static T Fn<T>(IntPtr image,string name) { IntPtr p=GetProcAddress(image,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static string Invoke(Entry entry,ulong mode) {
        var c=new Context();ulong value=entry(ref c,new[]{mode});Check(c.Kind==0&&c.Depth==0&&value!=0,"Object field caller failed mode="+mode+" kind="+c.Kind+" method="+c.Method+" pc="+c.PC);
        IntPtr text=new IntPtr(unchecked((long)value));Check(Marshal.ReadInt64(text,-16)==16&&Marshal.ReadInt32(text,-20)==1,"Object field result is not a String");
        IntPtr chars=Marshal.ReadIntPtr(text);Check(Marshal.ReadIntPtr(chars,-8).ToInt64()==261,"Object field result lacks UTF16 data");return Marshal.PtrToStringUni(chars,checked((int)(Marshal.ReadInt64(chars,-16)/2)));
    }
    public static string[] Run(string dll,string runtime) {
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"Object field image load failed");
        try {
            heap=Fn<Create>(rt,"boom_heap_create")(67108864);Check(heap!=IntPtr.Zero&&Fn<One>(image,"boom_bind_heap")(heap)==1,"Object field heap bind failed");var entry=Fn<Entry>(image,"boom_entry32");
            string[] results=new string[17];for(ulong mode=0;mode<16;mode++)results[mode]=Invoke(entry,mode);results[16]=Invoke(entry,18);
            Parallel.For(0,8,worker=>{for(int i=0;i<128;i++){ulong mode=(ulong)(i%16);if(mode==10)continue;Check(Invoke(entry,mode)==results[mode],"Parallel object fields differ at "+mode);}});
            Invoke(entry,16);Check(Invoke(entry,17)=="won"&&Invoke(entry,17)=="lost","Boolean atomic warmup differs");Invoke(entry,16);long before=Marshal.ReadInt64(heap,48);
            for(int round=0;round<512;round++) { Check(Invoke(entry,16)=="reset","Boolean reset failed");int winners=0;Parallel.For(0,8,worker=>{string result=Invoke(entry,17);if(result=="won")Interlocked.Increment(ref winners);else Check(result=="lost","Boolean contender returned invalid result");});Check(winners==1,"Boolean CAS publication was not atomic"); }
            Check(Marshal.ReadInt64(heap,48)==before,"Warm field lookup/boolean CAS allocated guest objects");return results;
        } finally { if(image!=IntPtr.Zero&&GetProcAddress(image,"boom_release_trace_pool")!=IntPtr.Zero)Check(Fn<Release>(image,"boom_release_trace_pool")()==0,"Object field frames remain");if(heap!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(heap);if(rt!=IntPtr.Zero)FreeLibrary(rt);if(image!=IntPtr.Zero)FreeLibrary(image); }
    }
}
