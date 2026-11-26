// Independent verification driver. All String, heap and worker execution is MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomConcatApiProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Get();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Service(ref Context c,[In] ulong[] a,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RawService(IntPtr c,IntPtr a,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool ok,string text) { if(!ok) throw new Exception(text); }
    static T Fn<T>(IntPtr m,string name) { IntPtr p=GetProcAddress(m,name); Check(p!=IntPtr.Zero,"Missing "+name); return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static IntPtr Open(string dll) { IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100); Check(m!=IntPtr.Zero,"Concat DLL failed to load"); return m; }
    static void Close(IntPtr m,IntPtr heap) { IntPtr p=GetProcAddress(m,"boom_release_trace_pool"); if(p!=IntPtr.Zero) Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"Concat frames still active"); if(heap!=IntPtr.Zero) Check(Fn<Destroy>(m,"boom_heap_destroy")(heap)!=0,"Concat heap failed to shut down"); FreeLibrary(m); }
    static int Reachable(IntPtr roots,uint count) {
        var seen=new HashSet<IntPtr>(); var todo=new Stack<IntPtr>();
        for(int i=0;i<count;i++) todo.Push(Marshal.ReadIntPtr(roots,8*i));
        while(todo.Count!=0) { IntPtr p=todo.Pop(); if(p==IntPtr.Zero||!seen.Add(p)) continue;
            uint tag=unchecked((uint)Marshal.ReadInt32(p,-24)),refs=unchecked((uint)Marshal.ReadInt32(p,-20)); long size=Marshal.ReadInt64(p,-16);
            Check((tag&0xfffffffd)==0xb00b0001&&size>=0&&refs<=(ulong)size/8&&seen.Count<1048576,"Concat graph is malformed");
            for(int i=0;i<refs;i++) todo.Push(Marshal.ReadIntPtr(p,8*i));
        } return seen.Count;
    }
    static long GC(IntPtr m,IntPtr heap,params IntPtr[] extra) {
        IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint n),roots=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));
        try { for(int i=0;i<n;i++) Marshal.WriteIntPtr(roots,i*8,Marshal.ReadIntPtr(statics,i*8)); for(int i=0;i<extra.Length;i++) Marshal.WriteIntPtr(roots,((int)n+i)*8,extra[i]);
            int expected=Reachable(roots,n+(uint)extra.Length); Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n+(uint)extra.Length)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==expected,"Concat collection lost live objects or retained temporary storage"); return expected;
        } finally { Marshal.FreeHGlobal(roots); }
    }
    static ulong Call(Entry entry,uint n) { var c=new Context(); ulong value=entry(ref c,new ulong[]{n}); Check(c.Kind==0&&c.Depth==0,"Concat guest call failed"); return value; }
    static ulong[] Args(IntPtr a,IntPtr b) { return new ulong[]{unchecked((ulong)a.ToInt64()),unchecked((ulong)b.ToInt64())}; }
    static void Text(IntPtr s,string expected) { IntPtr chars=Marshal.ReadIntPtr(s); Check(Marshal.ReadInt64(chars,-16)==expected.Length*2&&Marshal.PtrToStringUni(chars,expected.Length)==expected,"Concat UTF16 contents differ"); }
    public static void ObjectsAndFailures(string dll,string runtime) {
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,other=IntPtr.Zero,copy=IntPtr.Zero;
        try {
            heap=Fn<Create>(m,"boom_heap_create")(65536); Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Concat heap bind failed");
            var entry=Fn<Entry>(m,"boom_entry"); var service=Fn<Service>(m,"boom_string_concat_api");
            var values=new IntPtr[8]; for(uint i=0;i<8;i++) values[i]=new IntPtr(unchecked((long)Call(entry,i)));
            Text(values[0],"");Text(values[1],"abc");Text(values[2],"A");Text(values[3],"abc");Text(values[4],"abcA");Text(values[6],"abcabc");Text(values[7],"\ud800\0\udc00\ud83e\uddf1");
            Check(values[3]!=values[1]&&Marshal.ReadIntPtr(values[3])==Marshal.ReadIntPtr(values[1])&&values[5]==values[1],"Concat copy/empty-suffix identity changed");
            Check(Marshal.ReadIntPtr(values[4])!=Marshal.ReadIntPtr(values[1])&&Marshal.ReadIntPtr(values[6])!=Marshal.ReadIntPtr(values[1]),"Nonempty concat incorrectly reused backing storage");
            GC(m,heap,values); IntPtr stringPool=Fn<Get>(m,"boom_get_concat_string_pool")(); long live=Marshal.ReadInt64(heap,56);
            // Share a dynamic suffix, then retain only its fresh copy across collection.
            var c=new Context(); IntPtr shared=service(ref c,Args(values[0],values[4]),stringPool); Check(c.Kind==0&&shared!=values[4]&&Marshal.ReadIntPtr(shared)==Marshal.ReadIntPtr(values[4])&&Marshal.ReadInt64(heap,56)==live+1,"Dynamic copy must allocate exactly one String");
            GC(m,heap,shared);Text(shared,"abcA"); GC(m,heap); long baseline=Marshal.ReadInt64(heap,56);
            c=new Context(); Check(service(ref c,Args(values[1],values[0]),stringPool)==values[1]&&c.Kind==0&&Marshal.ReadInt64(heap,56)==baseline,"Empty suffix allocated");
            // Metadata gates apply even to the otherwise allocation-free path.
            copy=Marshal.AllocHGlobal(80); byte[] bytes=new byte[80];Marshal.Copy(stringPool,bytes,0,80);
            foreach(int field in new int[]{0,4,48,64}) { Marshal.Copy(bytes,0,copy,80);if(field<8)Marshal.WriteInt32(copy,field,0);else Marshal.WriteInt64(copy,field,0);c=new Context();Check(service(ref c,Args(values[1],values[0]),copy)==IntPtr.Zero&&c.Kind==7,"Malformed concat pool accepted"); }
            other=Fn<Create>(m,"boom_heap_create")(65536);Check(other!=IntPtr.Zero,"Second test heap failed");Marshal.Copy(bytes,0,copy,80);Marshal.WriteIntPtr(copy,48,other);c=new Context();Check(service(ref c,Args(values[1],values[0]),copy)==IntPtr.Zero&&c.Kind==7,"Foreign heap pool accepted");
            c=new Context{Kind=9,PC=123,Method=456,Depth=7};Check(service(ref c,Args(values[1],values[0]),stringPool)==IntPtr.Zero&&c.Kind==9&&c.PC==123&&c.Method==456&&c.Depth==7,"Pending concat error was overwritten");
            var raw=Fn<RawService>(m,"boom_string_concat_api");Check(raw(IntPtr.Zero,IntPtr.Zero,stringPool)==IntPtr.Zero,"NULL native context accepted");
            foreach(var pair in new ulong[][]{Args(IntPtr.Zero,values[1]),Args(values[0],IntPtr.Zero),Args(values[1],IntPtr.Zero)}) { c=new Context();Check(service(ref c,pair,stringPool)==IntPtr.Zero&&c.Kind==4,"Concat null check changed"); }
            // Leave exactly one 48-byte hole: char[] succeeds, String allocation fails.
            var alloc=Fn<Alloc>(r,"boom_heap_alloc"); var fillers=new List<IntPtr>();IntPtr p;
            while((p=alloc(heap,16,0,267))!=IntPtr.Zero){fillers.Add(p);Check(fillers.Count<4096,"Concat filler overflow");}
            while((p=alloc(heap,0,0,267))!=IntPtr.Zero){fillers.Add(p);Check(fillers.Count<4096,"Concat filler overflow");}
            Check(fillers.Count>4,"Concat partial OOM setup too small");fillers.RemoveAt(1);GC(m,heap,fillers.ToArray());long before=Marshal.ReadInt64(heap,56);
            c=new Context();Check(service(ref c,Args(values[1],values[2]),stringPool)==IntPtr.Zero&&c.Kind==3&&Marshal.ReadInt64(heap,56)==before+1,"Concat partial allocation failure path did not execute");
            GC(m,heap,fillers.ToArray());Check(Marshal.ReadInt64(heap,56)==before,"Failed concat char[] leaked");GC(m,heap);
            c=new Context();p=service(ref c,Args(values[1],values[2]),stringPool);Check(c.Kind==0&&p!=IntPtr.Zero,"Concat did not recover after OOM");Text(p,"abcA");GC(m,heap);
        } finally { if(copy!=IntPtr.Zero)Marshal.FreeHGlobal(copy);if(other!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(other)!=0,"Second heap shutdown failed");Close(m,heap);FreeLibrary(r); }
    }
    public static void AllocationPaths(string dll) {
        IntPtr m=Open(dll),heap=IntPtr.Zero;
        try { heap=Fn<Create>(m,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Allocation heap bind failed");var entry=Fn<Entry>(m,"boom_entry");for(uint i=0;i<4;i++)Call(entry,i);GC(m,heap);
            for(uint mode=0;mode<4;mode++)for(int i=0;i<64;i++){long before=Marshal.ReadInt64(heap,56);Check(Call(entry,mode)==new ulong[]{3,3,4,6}[mode]&&Marshal.ReadInt64(heap,56)==before+new int[]{0,1,2,2}[mode],"Concat allocation budget changed");GC(m,heap);}
        }finally{Close(m,heap);}
    }
    public static void FullHeap(string dll,string runtime) {
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Full concat heap bind failed");var entry=Fn<Entry>(m,"boom_entry");for(uint i=0;i<4;i++)Call(entry,i);GC(m,heap);
            var alloc=Fn<Alloc>(r,"boom_heap_alloc");int blocks=0;while(alloc(heap,4096,0,267)!=IntPtr.Zero)Check(++blocks<4096,"Full heap filler overflow");while(alloc(heap,0,0,267)!=IntPtr.Zero)Check(++blocks<4096,"Full heap filler overflow");long before=Marshal.ReadInt64(heap,56);
            for(uint i=0;i<256;i++)Check(Call(entry,i)==(i%4==0?3UL:89UL)&&Marshal.ReadInt64(heap,56)==before,"Full-heap concat identity/OOM catch allocated or failed");GC(m,heap);for(uint i=0;i<4;i++)Check(Call(entry,i)==new ulong[]{3,3,4,6}[i],"Concat source handler failed to recover");GC(m,heap);
        }finally{Close(m,heap);FreeLibrary(r);}
    }
    public static void Parallel(string dll,string runtime,int[] expected) {
        const int count=2049;IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{Check(expected.Length==count,"Concat parallel oracle size changed");heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Parallel concat heap bind failed");input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);for(int i=0;i<count;i++)Marshal.WriteInt64(input,i*128,i);pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Concat worker pool failed");var run=Fn<PoolRun>(r,"boom_pool_run");
            for(int batch=0;batch<3;batch++){Check(run(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Concat worker batch failed");for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked((uint)expected[i])&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Parallel concat mismatch: "+i);GC(m,heap);}
        }finally{if(pool!=IntPtr.Zero)Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(pool)==0,"Concat worker shutdown failed");if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);Close(m,heap);FreeLibrary(r);}
    }
}
