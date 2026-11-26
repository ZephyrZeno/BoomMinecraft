// Independent UTF16 oracle and heap tests; all guest execution is assembly.
using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomHexStringProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Service(ref Context c,[In] ulong[] a,IntPtr pool,uint width);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RawService(IntPtr c,IntPtr a,IntPtr pool,uint width);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Get();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string dll){IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Hex DLL failed to load");return m;}
    static void Close(IntPtr m,IntPtr heap){IntPtr p=GetProcAddress(m,"boom_release_trace_pool");if(p!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"Hex frames still active");if(heap!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(heap)!=0,"Hex heap shutdown failed");FreeLibrary(m);}
    static int Reachable(IntPtr roots,uint n){var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>();for(int i=0;i<n;i++)todo.Push(Marshal.ReadIntPtr(roots,i*8));while(todo.Count!=0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint flags=unchecked((uint)Marshal.ReadInt32(p,-24)),refs=unchecked((uint)Marshal.ReadInt32(p,-20));long bytes=Marshal.ReadInt64(p,-16);Check((flags&0xfffffffd)==0xb00b0001&&bytes>=0&&refs<=(ulong)bytes/8&&seen.Count<1048576,"Malformed hex graph");for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,i*8));}return seen.Count;}
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra){IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint n),roots=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(roots,i*8,Marshal.ReadIntPtr(statics,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(roots,((int)n+i)*8,extra[i]);uint count=n+(uint)extra.Length;int live=Reachable(roots,count);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,count)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==live,"Hex roots lost or temporary objects leaked");}finally{Marshal.FreeHGlobal(roots);}}
    static ulong Call(Entry entry,ulong n){var c=new Context();ulong v=entry(ref c,new ulong[]{n});Check(c.Kind==0&&c.Depth==0,"Hex source call failed");return v;}
    static string Text(IntPtr s){Check(s!=IntPtr.Zero&&Marshal.ReadInt64(s,-16)==16&&Marshal.ReadInt32(s,-20)==1,"Invalid hex String");IntPtr data=Marshal.ReadIntPtr(s);long bytes=Marshal.ReadInt64(data,-16);Check(Marshal.ReadInt64(data,-8)==261&&bytes>=2&&bytes<=32&&(bytes&1)==0,"Invalid hex UTF16 storage");return Marshal.PtrToStringUni(data,checked((int)bytes/2));}
    static uint BE32(BinaryReader r){byte[] b=r.ReadBytes(4);Check(b.Length==4,"Truncated hex oracle");return ((uint)b[0]<<24)|((uint)b[1]<<16)|((uint)b[2]<<8)|b[3];}
    static ulong BE64(BinaryReader r){return ((ulong)BE32(r)<<32)|BE32(r);}
    public static int[] RawOutputs(string intDll,string longDll,string oracle){
        IntPtr im=Open(intDll),lm=Open(longDll),ih=IntPtr.Zero,lh=IntPtr.Zero;int ni=0,nl=0;
        try{ih=Fn<Create>(im,"boom_heap_create")(1024*1024);lh=Fn<Create>(lm,"boom_heap_create")(1024*1024);Check(ih!=IntPtr.Zero&&lh!=IntPtr.Zero&&Fn<Bind>(im,"boom_bind_heap")(ih)==1&&Fn<Bind>(lm,"boom_bind_heap")(lh)==1,"Hex oracle heap bind failed");var ie=Fn<Entry>(im,"boom_entry");var le=Fn<Entry>(lm,"boom_entry");
            using(var r=new BinaryReader(File.OpenRead(oracle))){Check(BE32(r)==0x48455831,"Wrong hex oracle");for(;;){uint width=BE32(r);if(width==0)break;Check(width==32||width==64,"Wrong hex oracle width");ulong bits=BE64(r);int size=checked((int)BE32(r));Check(size>=1&&size<=16,"Wrong hex oracle length");var chars=new char[size];for(int i=0;i<size;i++){int hi=r.ReadByte(),lo=r.ReadByte();chars[i]=(char)((hi<<8)|lo);}IntPtr m=width==32?im:lm,heap=width==32?ih:lh;var entry=width==32?ie:le;IntPtr value=new IntPtr(unchecked((long)Call(entry,bits)));Check(Text(value)==new string(chars),"Hex UTF16 JVM mismatch, width="+width);GC(m,heap);if(width==32)ni++;else nl++;}Check(r.BaseStream.Position==r.BaseStream.Length,"Trailing hex oracle bytes");}
            return new int[]{ni,nl};
        }finally{Close(im,ih);Close(lm,lh);}
    }
    public static void AllocationAndFailures(string dll,string runtime){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,copy=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Hex allocation heap failed");var entry=Fn<Entry>(m,"boom_entry");Text(new IntPtr(unchecked((long)Call(entry,0))));GC(m,heap);var service=Fn<Service>(m,"boom_hex_string");IntPtr pool=Fn<Get>(m,"boom_get_hex_string_pool")();
            for(int i=0;i<256;i++){long before=Marshal.ReadInt64(heap,56);IntPtr a=new IntPtr(unchecked((long)Call(entry,(uint)i)));Check(Marshal.ReadInt64(heap,56)==before+2,"Hex allocation budget changed");var c=new Context();IntPtr b=service(ref c,new ulong[]{(uint)i},pool,32);Check(c.Kind==0&&a!=b&&Marshal.ReadIntPtr(a)!=Marshal.ReadIntPtr(b)&&Text(a)==Text(b),"Hex conversion reused mutable or observable identity");GC(m,heap);}
            copy=Marshal.AllocHGlobal(80);byte[] bytes=new byte[80];Marshal.Copy(pool,bytes,0,80);foreach(uint width in new uint[]{0,1,16,31,33,63,65,uint.MaxValue}){var c=new Context();Check(service(ref c,new ulong[]{1},pool,width)==IntPtr.Zero&&c.Kind==7,"Invalid hex width accepted");}
            Marshal.Copy(bytes,0,copy,80);Marshal.WriteInt32(copy,4,2);var bad=new Context();Check(service(ref bad,new ulong[]{1},copy,32)==IntPtr.Zero&&bad.Kind==7,"Legacy pool accepted by hex service");bad=new Context{Kind=9,PC=123,Method=456,Depth=7};Check(service(ref bad,new ulong[]{1},pool,32)==IntPtr.Zero&&bad.Kind==9&&bad.PC==123&&bad.Method==456&&bad.Depth==7,"Pending hex error overwritten");Check(Fn<RawService>(m,"boom_hex_string")(IntPtr.Zero,IntPtr.Zero,pool,32)==IntPtr.Zero,"NULL hex context accepted");
            var alloc=Fn<Alloc>(r,"boom_heap_alloc");var fillers=new List<IntPtr>();IntPtr p;while((p=alloc(heap,16,0,267))!=IntPtr.Zero){fillers.Add(p);Check(fillers.Count<4096,"Hex filler overflow");}while((p=alloc(heap,0,0,267))!=IntPtr.Zero){fillers.Add(p);Check(fillers.Count<4096,"Hex filler overflow");}Check(fillers.Count>4,"Hex partial OOM setup too small");fillers.RemoveAt(1);GC(m,heap,fillers.ToArray());long objects=Marshal.ReadInt64(heap,56);bad=new Context();Check(service(ref bad,new ulong[]{0},pool,32)==IntPtr.Zero&&bad.Kind==3&&Marshal.ReadInt64(heap,56)==objects+1,"Hex second allocation failure path not executed");GC(m,heap,fillers.ToArray());Check(Marshal.ReadInt64(heap,56)==objects,"Hex partial char[] leaked");GC(m,heap);bad=new Context();p=service(ref bad,new ulong[]{uint.MaxValue},pool,32);Check(bad.Kind==0&&Text(p)=="ffffffff","Hex OOM recovery failed");GC(m,heap);
        }finally{if(copy!=IntPtr.Zero)Marshal.FreeHGlobal(copy);Close(m,heap);FreeLibrary(r);}
    }
    public static void FullHeap(string dll,string runtime,uint width){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Hex full heap bind failed");var entry=Fn<Entry>(m,"boom_entry");Check(Call(entry,0)==1,"Hex OOM warmup failed");GC(m,heap);var alloc=Fn<Alloc>(r,"boom_heap_alloc");int blocks=0;while(alloc(heap,4096,0,267)!=IntPtr.Zero)Check(++blocks<4096,"Hex filler overflow");while(alloc(heap,0,0,267)!=IntPtr.Zero)Check(++blocks<4096,"Hex filler overflow");long before=Marshal.ReadInt64(heap,56);for(ulong i=0;i<128;i++)Check(Call(entry,i)==89&&Marshal.ReadInt64(heap,56)==before,"Full-heap hex did not catch OOM without allocation");GC(m,heap);Check(Call(entry,ulong.MaxValue)==(width==32?8UL:16UL),"Hex full-heap source recovery failed");GC(m,heap);
        }finally{Close(m,heap);FreeLibrary(r);}
    }
    public static void Parallel(string dll,string runtime,int[] expected){
        const int count=2049;IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{Check(expected.Length==count,"Hex parallel oracle changed");heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Hex parallel heap failed");input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);for(int i=0;i<count;i++)Marshal.WriteInt64(input,128*i,i);pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Hex worker pool failed");var run=Fn<PoolRun>(r,"boom_pool_run");for(int batch=0;batch<3;batch++){Check(run(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Hex worker run failed");for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,32*i))==unchecked((uint)expected[i])&&Marshal.ReadInt64(output,32*i+8)==0&&Marshal.ReadInt64(output,32*i+16)==0&&Marshal.ReadInt64(output,32*i+24)==0,"Hex parallel mismatch: "+i);GC(m,heap);}
        }finally{if(pool!=IntPtr.Zero)Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(pool)==0,"Hex worker shutdown failed");if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);Close(m,heap);FreeLibrary(r);}
    }
}
