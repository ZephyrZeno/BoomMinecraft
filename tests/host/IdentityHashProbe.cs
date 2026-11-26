// Independent host checks; hashing, guest memory and worker execution are MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomIdentityHashProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint c,uint f);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Hash(ref Context c,IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint RawHash(IntPtr c,IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool ok,string s) { if(!ok) throw new Exception(s); }
    static T Fn<T>(IntPtr m,string name) { IntPtr p=GetProcAddress(m,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static IntPtr Open(string dll) { IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Hash DLL load failed");return m; }
    static void Close(IntPtr m,IntPtr heap) { IntPtr p=GetProcAddress(m,"boom_release_trace_pool");if(p!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"Hash Java frames still active");if(heap!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(heap)!=0,"Hash heap shutdown failed");FreeLibrary(m); }
    static int Reachable(IntPtr roots,uint n) {
        var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>();for(int i=0;i<n;i++)todo.Push(Marshal.ReadIntPtr(roots,i*8));
        while(todo.Count!=0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint flags=unchecked((uint)Marshal.ReadInt32(p,-24)),refs=unchecked((uint)Marshal.ReadInt32(p,-20));long size=Marshal.ReadInt64(p,-16);Check((flags&0xfffffffd)==0xb00b0001&&size>=0&&refs<=(ulong)size/8&&seen.Count<1048576,"Malformed identity test graph");for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,i*8));}return seen.Count;
    }
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra) {
        IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));
        try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,8*i,Marshal.ReadIntPtr(statics,8*i));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,8*((int)n+i),extra[i]);uint count=n+(uint)extra.Length;int expected=Reachable(all,count);Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,count)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==expected,"Identity roots lost or temporary objects leaked");}finally{Marshal.FreeHGlobal(all);}
    }
    static ulong Call(Entry entry,uint n) { var c=new Context();ulong value=entry(ref c,new ulong[]{n});Check(c.Kind==0&&c.Depth==0,"Identity source call failed");return value; }
    static uint Value(Hash hash,IntPtr obj) { var c=new Context();uint value=hash(ref c,obj);Check(c.Kind==0&&c.Depth==0,"Native identity call failed");return value; }
    public static void ObjectsAndGC(string dll) {
        IntPtr m=Open(dll),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Identity object heap bind failed");var entry=Fn<Entry>(m,"boom_entry");var hash=Fn<Hash>(m,"boom_identity_hash");var objects=new IntPtr[8];var values=new uint[8];
            for(uint i=0;i<8;i++){objects[i]=new IntPtr(unchecked((long)Call(entry,i)));Check(objects[i]!=IntPtr.Zero,"Identity factory returned NULL");values[i]=Value(hash,objects[i]);Check(values[i]>0&&values[i]<=int.MaxValue,"Non-NULL identity outside native contract");}
            GC(m,heap,objects);long live=Marshal.ReadInt64(heap,56),used=Marshal.ReadInt64(heap,48);
            for(int i=0;i<8193;i++)Check(Value(hash,objects[i&7])==values[i&7],"Identity changed without moving the object");Check(Marshal.ReadInt64(heap,56)==live&&Marshal.ReadInt64(heap,48)==used,"Native identity hashing allocated guest memory");GC(m,heap,objects);
            for(int i=0;i<8;i++)Check(Value(hash,objects[i])==values[i],"Identity changed after quiescent collection");
            var retained=new IntPtr[1032];Array.Copy(objects,retained,8);var hashes=new HashSet<uint>();
            for(uint i=0;i<1024;i++){retained[i+8]=new IntPtr(unchecked((long)Call(entry,(i<<3)|1)));hashes.Add(Value(hash,retained[i+8]));}
            Check(hashes.Count>=1000,"Identity mix collapsed the allocator's aligned addresses");GC(m,heap,retained);
            Check(Value(hash,IntPtr.Zero)==0,"NULL identity is not zero");var c=new Context{Kind=9,PC=123,Method=456,Depth=7};Check(hash(ref c,objects[0])==0&&c.Kind==9&&c.PC==123&&c.Method==456&&c.Depth==7,"Pending identity error was overwritten");Check(Fn<RawHash>(m,"boom_identity_hash")(IntPtr.Zero,objects[0])==0,"NULL native context accepted");GC(m,heap);
        }finally{Close(m,heap);}
    }
    public static void FullHeapNoAllocation(string dll,string runtime) {
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Identity hot heap bind failed");var entry=Fn<Entry>(m,"boom_entry");Check(Call(entry,0)==37,"Identity hot source warmup failed");GC(m,heap);var alloc=Fn<Alloc>(r,"boom_heap_alloc");int blocks=0;while(alloc(heap,4096,0,267)!=IntPtr.Zero)Check(++blocks<4096,"Identity filler overflow");while(alloc(heap,0,0,267)!=IntPtr.Zero)Check(++blocks<4096,"Identity filler overflow");long live=Marshal.ReadInt64(heap,56),used=Marshal.ReadInt64(heap,48);
            for(uint i=0;i<8193;i++)Check(Call(entry,i)==i+37,"Identity source failed on a full heap");Check(Marshal.ReadInt64(heap,56)==live&&Marshal.ReadInt64(heap,48)==used,"Identity source allocated on the full heap");GC(m,heap);Check(Call(entry,17)==54,"Identity source failed after collection");GC(m,heap);
        }finally{Close(m,heap);FreeLibrary(r);}
    }
    public static void Parallel(string dll,string runtime,int[] expected,uint owner,uint syncField,int callsOffset) {
        const int count=2049;IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{Check(expected.Length==count,"Identity parallel oracle changed");heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Identity parallel heap bind failed");input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);for(int i=0;i<count;i++)Marshal.WriteInt64(input,128*i,i);pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Identity worker pool failed");var run=Fn<PoolRun>(r,"boom_pool_run");
            for(int batch=0;batch<3;batch++){Check(run(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Identity worker batch failed");for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,32*i))==unchecked((uint)expected[i])&&Marshal.ReadInt64(output,32*i+8)==0&&Marshal.ReadInt64(output,32*i+16)==0&&Marshal.ReadInt64(output,32*i+24)==0,"Identity worker result mismatch: "+i);GC(m,heap);}
            IntPtr cell=Fn<Field>(m,"boom_get_static_field")(owner,syncField);Check(cell!=IntPtr.Zero,"Missing synchronized hash root");IntPtr sync=Marshal.ReadIntPtr(cell);Check(sync!=IntPtr.Zero&&Marshal.ReadInt32(sync,callsOffset)==6147,"Synchronized hash override lost calls or identityHashCode invoked an override");
        }finally{if(pool!=IntPtr.Zero)Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(pool)==0,"Identity workers failed to stop");if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);Close(m,heap);FreeLibrary(r);}
    }
}
