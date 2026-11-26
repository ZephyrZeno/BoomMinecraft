// Independent driver only. Unicode lookup, String operations, pool and GC are MASM.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
public static class BoomCaseProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Mapping(uint cp,uint direction);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,uint type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool ok,string s){if(!ok)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Case DLL load failed");return m;}
    static void ReleaseFrames(IntPtr m){IntPtr p=GetProcAddress(m,"boom_release_trace_pool");if(p!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"Case Java frames remained active at shutdown");}
    static uint BE(byte[] b,int i){return ((uint)b[i]<<24)|((uint)b[i+1]<<16)|((uint)b[i+2]<<8)|b[i+3];}
    public static void AllMappings(string runtime,string oracle){
        byte[] bytes=File.ReadAllBytes(oracle);Check(bytes.Length>=8&&BE(bytes,0)==0x55434331&&bytes.Length==8+BE(bytes,4)*12,"Malformed Unicode/JDK oracle");
        IntPtr m=Open(runtime);try{var map=Fn<Mapping>(m,"boom_unicode_case");int row=8;for(uint cp=0;cp<0x110000;cp++){uint upper=cp,lower=cp;if(row<bytes.Length&&BE(bytes,row)==cp){upper=BE(bytes,row+4);lower=BE(bytes,row+8);row+=12;}Check(map(cp,0)==upper&&map(cp,1)==lower,"ASM Unicode/JDK mismatch: "+cp.ToString("x"));}Check(row==bytes.Length,"Unsorted Unicode reference");foreach(uint cp in new uint[]{0x110000,uint.MaxValue,0x80000000})Check(map(cp,0)==cp&&map(cp,1)==cp,"Out-of-range code point changed bits");Check(map(65,2)==65,"Unknown case direction changed bits");}finally{FreeLibrary(m);}
    }
    static int Reachable(IntPtr roots,uint n){var seen=new HashSet<IntPtr>();var stack=new Stack<IntPtr>();for(int i=0;i<n;i++)stack.Push(Marshal.ReadIntPtr(roots,i*8));while(stack.Count!=0){IntPtr v=stack.Pop();if(v==IntPtr.Zero||!seen.Add(v))continue;uint refs=unchecked((uint)Marshal.ReadInt32(v,-20)),flags=unchecked((uint)Marshal.ReadInt32(v,-24));long size=Marshal.ReadInt64(v,-16);Check((flags&0xfffffffd)==0xb00b0001&&size>=0&&refs<=(ulong)size/8&&seen.Count<1048576,"Invalid case graph");for(int i=0;i<refs;i++)stack.Push(Marshal.ReadIntPtr(v,i*8));}return seen.Count;}
    static void GC(IntPtr m,IntPtr heap){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);int live=Reachable(roots,n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==live,"Case graph lost or temporary strings leaked");}
    public static void ParallelAndNoAllocation(string dll,string runtime,int[] expected){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;const int count=2049;
        try{Check(expected.Length==count,"Case parallel oracle size mismatch");heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Case heap bind failed");input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);for(int i=0;i<count;i++)Marshal.WriteInt64(input,i*128,i);pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Case worker pool failed");var run=Fn<PoolRun>(r,"boom_pool_run");
            for(int batch=0;batch<3;batch++){Check(run(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Case worker batch failed");for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked((uint)expected[i])&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Case worker mismatch: "+i);GC(m,heap);}
            long objects=Marshal.ReadInt64(heap,56),used=Marshal.ReadInt64(heap,48);var entry=Fn<Entry>(m,"boom_entry");for(int i=0;i<4099;i++){var c=new Context();Check(unchecked((uint)entry(ref c,new ulong[]{(uint)(i%count)}))==unchecked((uint)expected[i%count])&&c.Kind==0&&c.Depth==0,"Hot case result mismatch");}Check(Marshal.ReadInt64(heap,56)==objects&&Marshal.ReadInt64(heap,48)==used,"Read-only Unicode comparison allocated guest storage");GC(m,heap);
        }finally{if(pool!=IntPtr.Zero)Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(pool)==0,"Case pool shutdown failed");if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(heap)!=0,"Case heap shutdown failed");FreeLibrary(m);FreeLibrary(r);}
    }
    public static void FullHeapSubstring(string dll,string runtime){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Substring OOM heap failed");var entry=Fn<Entry>(m,"boom_entry");var c=new Context();Check(entry(ref c,new ulong[]{0})==12&&c.Kind==0,"Substring warmup failed");GC(m,heap);var alloc=Fn<Alloc>(r,"boom_heap_alloc");int blocks=0;while(alloc(heap,4096,0,267)!=IntPtr.Zero){Check(++blocks<1000,"Substring heap budget exceeded");}while(alloc(heap,0,0,267)!=IntPtr.Zero){Check(++blocks<4096,"Substring heap budget exceeded");}long before=Marshal.ReadInt64(heap,56);c=new Context();Check(entry(ref c,new ulong[]{0})==89&&c.Kind==0&&c.Depth==0&&Marshal.ReadInt64(heap,56)==before,"Full-heap substring did not catch OOM without further allocation");GC(m,heap);c=new Context();Check(entry(ref c,new ulong[]{0})==12&&c.Kind==0,"Substring failed to recover after collection");GC(m,heap);
        }finally{ReleaseFrames(m);if(heap!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(heap)!=0,"Substring OOM heap shutdown failed");FreeLibrary(m);FreeLibrary(r);}
    }
}
