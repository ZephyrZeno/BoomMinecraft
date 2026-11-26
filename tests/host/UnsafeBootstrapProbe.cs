// Test controller only. Guest initialization, atomic loops and native services
// execute the self-written AOT backend and assembly runtime.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

public static class BoomUnsafeBootstrapProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int End(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Get();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Indexed(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint c,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Native(ref Context c,[In] ulong[] args,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RegCreate(IntPtr h,uint max);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Next(IntPtr r);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool ok,string msg) { if(!ok) throw new Exception(msg); }
    static IntPtr Open(string path) { IntPtr m=LoadLibraryExW(path,IntPtr.Zero,0x1100); Check(m!=IntPtr.Zero,"Unsafe image load failed"); return m; }
    static T Fn<T>(IntPtr m,string n) { IntPtr p=GetProcAddress(m,n); Check(p!=IntPtr.Zero,"Missing "+n); return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static ulong Bits(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    static ulong Call(Entry fn,ulong[] args) { var c=new Context(); ulong v=fn(ref c,args); Check(c.Kind==0,"Unsafe AOT error "+c.Kind+" pc "+c.PC+" method "+c.Method); return v; }
    static void ReleaseFrames(IntPtr m) { IntPtr p=GetProcAddress(m,"boom_release_trace_pool"); if(p!=IntPtr.Zero) Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"Unsafe frames remain active"); }
    static void Workers(IntPtr m,Action<int> action) {
        Exception error=null; object gate=new object(); var threads=new Thread[8];
        for(int w=0;w<8;w++) { int worker=w; threads[w]=new Thread(()=> {try { action(worker); } catch(Exception e) {lock(gate) {error=error??e;} }}); threads[w].Start(); }
        foreach(Thread t in threads) t.Join(); if(error!=null) throw error;
    }
    static void GC(IntPtr m,IntPtr heap,IntPtr extra) {
        IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint n); var roots=new List<IntPtr>();
        for(int i=0;i<n;i++) roots.Add(Marshal.ReadIntPtr(statics,i*8)); if(extra!=IntPtr.Zero) roots.Add(extra);
        var seen=new HashSet<IntPtr>(); var todo=new Stack<IntPtr>(roots);
        while(todo.Count>0) {IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint refs=unchecked((uint)Marshal.ReadInt32(p,-20));for(uint i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,checked((int)i*8)));}
        IntPtr buffer=Marshal.AllocHGlobal(roots.Count*8);
        try {for(int i=0;i<roots.Count;i++)Marshal.WriteIntPtr(buffer,i*8,roots[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,buffer,(uint)roots.Count)!=ulong.MaxValue,"Unsafe GC failed");Check((ulong)Marshal.ReadInt64(heap,56)==(ulong)seen.Count,"Unsafe independent root graph differs");} finally {Marshal.FreeHGlobal(buffer);}
    }
    static void Cleanup(IntPtr m,IntPtr r,IntPtr heap) {ReleaseFrames(m);if(heap!=IntPtr.Zero)Check(Fn<End>(r,"boom_heap_destroy")(heap)!=0,"Unsafe heap cleanup failed");FreeLibrary(m);FreeLibrary(r);}
    public static void Initialize(string image,string runtime,uint owner,uint constants,uint[] fieldIds,uint[] constantIds) {
        IntPtr m=Open(image),r=Open(runtime),heap=IntPtr.Zero;
        try {
            heap=Fn<Create>(r,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Unsafe heap bind failed");
            Entry entry=Fn<Entry>(m,"boom_entry");var values=new ulong[6147];
            Workers(m,w=>{for(int i=w;i<values.Length;i+=8)values[i]=Call(entry,Array.Empty<ulong>());});
            Check(values[0]!=0,"Unsafe singleton missing");foreach(ulong v in values)Check(v==values[0],"Unsafe singleton identity changed");
            Field field=Fn<Field>(m,"boom_get_static_field");
            long[] expected={0,0,0,0,0,0,0,0,0,1,1,2,2,4,8,4,8,8,8};
            Check(fieldIds.Length==expected.Length,"Unsafe field list differs");
            for(int i=0;i<expected.Length;i++)Check(Marshal.ReadInt64(field(owner,fieldIds[i]))==expected[i],"Unsafe array layout field differs at "+i);
            long[] vm={8,Environment.SystemPageSize,0,1,0};
            for(int i=0;i<vm.Length;i++)Check(Marshal.ReadInt64(field(constants,constantIds[i]))==vm[i],"Unsafe VM constant differs at "+i);
            Check(Marshal.ReadInt32(Fn<Indexed>(m,"boom_get_class_descriptor")(owner),8)==2&&Marshal.ReadInt32(Fn<Indexed>(m,"boom_get_class_descriptor")(constants),8)==2,"Unsafe source initialization incomplete");
            long before=Marshal.ReadInt64(heap,56);for(int i=0;i<128;i++)Check(Call(entry,Array.Empty<ulong>())==values[0],"Unsafe warm identity differs");Check(Marshal.ReadInt64(heap,56)==before,"Unsafe warm getter allocated");
            GC(m,heap,IntPtr.Zero);Check(Call(entry,Array.Empty<ulong>())==values[0],"Unsafe singleton lost after GC");
        } finally {Cleanup(m,r,heap);}
    }
    static uint U32(BinaryReader r) {uint v=0;for(int i=0;i<4;i++)v=(v<<8)|r.ReadByte();return v;}
    static ulong U64(BinaryReader r) {ulong v=0;for(int i=0;i<8;i++)v=(v<<8)|r.ReadByte();return v;}
    public static void Atomics(string image,string runtime,string oracle,uint owner,uint singletonField) {
        IntPtr m=Open(image),r=Open(runtime),heap=IntPtr.Zero;
        try {
            heap=Fn<Create>(r,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Atomic heap bind failed");
            Entry entry=Fn<Entry>(m,"boom_entry");Alloc alloc=Fn<Alloc>(m,"boom_heap_alloc");IntPtr array=alloc(heap,32,0,267);Check(array!=IntPtr.Zero,"Atomic array allocation failed");
            for(int repeat=0;repeat<2;repeat++) {
                using(var reader=new BinaryReader(File.OpenRead(oracle))) for(int i=0;i<1024;i++) {
                    uint op=U32(reader),index=U32(reader);ulong start=U64(reader),expected=U64(reader),delta=U64(reader),result=U64(reader),final=U64(reader);
                    for(int j=0;j<4;j++)Marshal.WriteInt64(array,j*8,0);Marshal.WriteInt64(array,(int)index*8,unchecked((long)start));
                    Check(Call(entry,new[]{Bits(array),(ulong)index,expected,delta,(ulong)op})==result,"Unsafe JVM return mismatch "+i);
                    Check(unchecked((ulong)Marshal.ReadInt64(array,(int)index*8))==final,"Unsafe JVM memory mismatch "+i);
                    for(int j=0;j<4;j++)if(j!=index)Check(Marshal.ReadInt64(array,j*8)==0,"Unsafe wrote an adjacent element");
                }
                GC(m,heap,array);
            }
            Marshal.WriteInt64(array,0,0);var records=new ulong[6147];long before=Marshal.ReadInt64(heap,56);
            Workers(m,w=>{for(int i=w;i<records.Length;i+=8)records[i]=Call(entry,new[]{Bits(array),0UL,0UL,1UL,2UL});});
            var seen=new HashSet<ulong>(records);Check(seen.Count==6147&&Marshal.ReadInt64(array)==6147,"Unsafe concurrent additions lost updates");for(ulong i=0;i<6147;i++)Check(seen.Contains(i),"Unsafe atomic previous values differ");Check(Marshal.ReadInt64(heap,56)==before,"Unsafe atomic loop allocated guest memory");
            IntPtr pool=Fn<Get>(m,"boom_get_unsafe_pool")();Native native=Fn<Native>(m,"boom_unsafe_native");IntPtr singleton=Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(owner,singletonField));
            foreach(ulong offset in new[]{1UL,32UL,ulong.MaxValue}) {var c=new Context();native(ref c,new[]{Bits(singleton),Bits(array),offset},pool,3);Check(c.Kind==18,"Unsafe invalid offset was accepted");}
            var pending=new Context{Kind=9,PC=17,Method=23,Pending=99,Plan=111};native(ref pending,Array.Empty<ulong>(),pool,3);Check(pending.Kind==9&&pending.PC==17&&pending.Method==23&&pending.Pending==99&&pending.Plan==111,"Unsafe overwrote pending context");
            var nullReceiver=new Context();native(ref nullReceiver,new[]{0UL,Bits(array),0UL},pool,3);Check(nullReceiver.Kind==4,"Unsafe null receiver accepted");
            var rawAddress=new Context();native(ref rawAddress,new[]{Bits(singleton),0UL,0x12345678UL},pool,3);Check(rawAddress.Kind==20,"Unsafe arbitrary raw address accepted");
            var wrongObject=new Context();native(ref wrongObject,new[]{Bits(singleton),Bits(singleton),0UL},pool,3);Check(wrongObject.Kind==20,"Unsafe unsupported object memory accepted");
            IntPtr other=Fn<Create>(r,"boom_heap_create")(65536);try {IntPtr foreign=alloc(other,32,0,267);var c=new Context();native(ref c,new[]{Bits(singleton),Bits(foreign),0UL},pool,3);Check(c.Kind==7,"Unsafe foreign heap accepted");}finally{Check(Fn<End>(r,"boom_heap_destroy")(other)!=0,"Foreign heap destroy failed");}
            while(alloc(heap,1024,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}
            before=Marshal.ReadInt64(heap,56);long initial=Marshal.ReadInt64(array);for(int i=0;i<8193;i++)Check(Call(entry,new[]{Bits(array),0UL,0UL,1UL,2UL})==unchecked((ulong)(initial+i)),"Unsafe full heap addition failed");Check(Marshal.ReadInt64(heap,56)==before,"Unsafe full heap operation allocated");
            GC(m,heap,array);Check(Call(entry,new[]{Bits(array),0UL,0UL,0UL,0UL})==unchecked((ulong)(initial+8193)),"Unsafe GC changed atomic value");
        } finally {Cleanup(m,r,heap);}
    }
    public static void ThreadIds(string image,string runtime) {
        IntPtr m=Open(image),r=Open(runtime),heap=IntPtr.Zero,registry=IntPtr.Zero;
        try {
            heap=Fn<Create>(r,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Thread ID heap bind failed");
            registry=Fn<RegCreate>(m,"boom_threads_create")(heap,8);Check(registry!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_thread_registry")(registry)==0,"Thread ID registry bind failed");
            Entry entry=Fn<Entry>(m,"boom_entry");var ids=new ulong[6147];Workers(m,w=>{for(int i=w;i<ids.Length;i+=8)ids[i]=Call(entry,Array.Empty<ulong>());});
            var seen=new HashSet<ulong>(ids);Check(seen.Count==ids.Length,"Source Thread IDs collided");for(ulong i=2;i<6149;i++)Check(seen.Contains(i),"Source Thread ID range differs");
            Check(Fn<Next>(m,"boom_threads_next_id")(registry)==6149&&Call(entry,Array.Empty<ulong>())==6150,"Source and VM Thread counters differ");
            GC(m,heap,IntPtr.Zero);Check(Call(entry,Array.Empty<ulong>())==6151,"Source ID state lost after GC");
            Check(Fn<Bind>(m,"boom_bind_thread_registry")(IntPtr.Zero)==0,"Thread ID unbind failed");Check(Fn<End>(m,"boom_threads_destroy")(registry)==0,"Thread ID registry cleanup failed");registry=IntPtr.Zero;
        } finally {if(registry!=IntPtr.Zero){Fn<Bind>(m,"boom_bind_thread_registry")(IntPtr.Zero);Fn<End>(m,"boom_threads_destroy")(registry);}Cleanup(m,r,heap);}
    }
}
