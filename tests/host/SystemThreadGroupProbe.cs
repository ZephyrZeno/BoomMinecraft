using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomSystemThreadGroupProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr zero,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Root(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint TraceRelease();
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Cannot load group image");return m;}
    static IntPtr Call(Entry e){var c=new Context();ulong p=e(ref c,Array.Empty<ulong>());Check(c.Kind==0&&c.Depth==0&&p!=0,"Original ThreadGroup constructor failed");return new IntPtr(unchecked((long)p));}
    static IntPtr Fields(IntPtr p,int[] offsets,string name){Check(Marshal.ReadIntPtr(p,offsets[0])==IntPtr.Zero&&Marshal.ReadIntPtr(p,offsets[2])==IntPtr.Zero&&Marshal.ReadIntPtr(p,offsets[3])==IntPtr.Zero&&Marshal.ReadInt32(p,offsets[4])==10&&Marshal.ReadInt32(p,offsets[5])==0&&Marshal.ReadInt32(p,offsets[6])==0&&Marshal.ReadByte(p,offsets[7])==0,"Original ThreadGroup fields differ from JVM");IntPtr text=Marshal.ReadIntPtr(p,offsets[1]),chars=Marshal.ReadIntPtr(text);int length=checked((int)(Marshal.ReadInt64(chars,-16)/2));var units=new char[length];for(int i=0;i<length;i++)units[i]=unchecked((char)Marshal.ReadInt16(chars,i*2));Check(new string(units)==name,"System group name differs from JVM");return text;}
    static void GC(IntPtr m,IntPtr heap,IntPtr held){IntPtr source=Fn<Root>(m,"boom_get_static_roots")(out uint n),roots=Marshal.AllocHGlobal(checked((int)(n+1)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(roots,i*8,Marshal.ReadIntPtr(source,i*8));Marshal.WriteIntPtr(roots,(int)n*8,held);var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>();for(int i=0;i<=n;i++)todo.Push(Marshal.ReadIntPtr(roots,i*8));while(todo.Count>0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint flags=unchecked((uint)Marshal.ReadInt32(p,-24)),refs=unchecked((uint)Marshal.ReadInt32(p,-20));Check((flags&0xfffffffd)==0xb00b0001&&refs<=(ulong)Marshal.ReadInt64(p,-16)/8,"Group root graph invalid");for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,i*8));}Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n+1)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==seen.Count,"Group root graph lost an object");}finally{Marshal.FreeHGlobal(roots);}}
    public static void Run(string image,string runtime,int[] offsets,string name){IntPtr m=Open(image),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;try{
        Check(offsets.Length==8&&name=="system","Group layout/oracle changed");heap=Fn<Create>(m,"boom_heap_create")(4*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Group heap setup failed");
        const int count=2049;pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Group native worker setup failed");input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);for(int i=0;i<count*128;i+=8)Marshal.WriteInt64(input,i,0);
        var unique=new HashSet<IntPtr>();IntPtr nameIdentity=IntPtr.Zero,held=IntPtr.Zero;
        for(int batch=0;batch<3;batch++){Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Group constructor worker batch failed");for(int i=0;i<count;i++){IntPtr p=Marshal.ReadIntPtr(output,i*32);Check(p!=IntPtr.Zero&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0&&unique.Add(p),"Cold group constructor results duplicated/failed");IntPtr text=Fields(p,offsets,name);if(nameIdentity==IntPtr.Zero){nameIdentity=text;held=p;}Check(text==nameIdentity,"Original literal identity was not shared");}}
        Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(pool)==0,"Group workers did not join");pool=IntPtr.Zero;GC(m,heap,held);Check(Fields(held,offsets,name)==nameIdentity,"Group fields changed after GC");
        var entry=Fn<Entry>(m,"boom_entry");for(int i=0;i<128;i++){long before=Marshal.ReadInt64(heap,56);Fields(Call(entry),offsets,name);Check(Marshal.ReadInt64(heap,56)==before+1,"Warm constructor allocated other than one group");}
        var alloc=Fn<Alloc>(r,"boom_heap_alloc");while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}
        for(int i=0;i<64;i++){var c=new Context();Check(entry(ref c,Array.Empty<ulong>())==0&&c.Kind==3&&c.Depth==0,"Full heap original group OOM did not propagate");}
        GC(m,heap,held);Check(Fields(Call(entry),offsets,name)==nameIdentity,"Original group did not recover after OOM/GC");
    }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);IntPtr release=GetProcAddress(m,"boom_release_trace_pool");if(release!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<TraceRelease>(release)()==0,"Group frames remain active");if(heap!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(heap)!=0,"Group heap cleanup failed");FreeLibrary(r);FreeLibrary(m);}}
}
