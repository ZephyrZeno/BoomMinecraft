// Test controller only. The retained Java getter and VM field execute in MASM.
// Abstract ClassLoader storage below is an explicit preconstructor VM fixture.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomClassLoaderProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Query(ref Context c,[In] ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Bind(IntPtr p,uint id,IntPtr loader);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Enter(IntPtr p,IntPtr node,IntPtr row,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Leave(IntPtr p,IntPtr node,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr h,IntPtr p,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Register(ref Context c,IntPtr p);
    static void Check(bool v,string why) { if(!v) throw new Exception(why); }
    static T Fn<T>(IntPtr m,string n) { IntPtr p=GetProcAddress(m,n); Check(p!=IntPtr.Zero,"Missing "+n); return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static IntPtr Storage(Alloc alloc,IntPtr heap,IntPtr tag) { return alloc(heap,(ulong)Marshal.ReadInt64(tag,8),(uint)Marshal.ReadInt32(tag,16),tag); }
    static ulong Bits(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    public static void RunRegistration(string dll) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,copy=IntPtr.Zero;
        Check(m!=IntPtr.Zero,"Class loader registration image load failed");
        try {
            heap=Fn<Create>(m,"boom_heap_create")(1048576);
            Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Registration heap bind failed");
            IntPtr pool=Fn<Pointer>(m,"boom_get_class_loader_native_pool")();
            var register=Fn<Register>(m,"boom_class_loader_register");
            Check(Marshal.ReadInt32(pool,8)==0,"Registration published before class initialization");
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};
            register(ref pending,pool);
            Check(pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678&&Marshal.ReadInt32(pool,8)==0,"Pending registration changed context or publication");
            var entry=Fn<Entry>(m,"boom_entry32");
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=> {
                for(int i=0;i<64;i++) { var c=new Context(); Check(entry(ref c,new[]{0UL}).ToInt64()==1&&c.Kind==0&&c.Depth==0,"Original ClassLoader initializer/checkName failed: "+c.Kind); }
            });
            Check(Marshal.ReadInt32(pool,8)==2&&Marshal.ReadInt32(pool,12)==1&&Marshal.ReadIntPtr(pool,16)==GetProcAddress(m,"boom_class_loader_retrieve"),"ClassLoader registration table differs");
            for(int i=0;i<256;i++) { var c=new Context(); register(ref c,pool); Check(c.Kind==0&&Marshal.ReadInt32(pool,8)==2,"Idempotent registration failed"); }
            copy=Marshal.AllocHGlobal(32); var bytes=new byte[32]; Marshal.Copy(pool,bytes,0,32); Marshal.Copy(bytes,0,copy,32);
            Marshal.WriteIntPtr(copy,16,IntPtr.Zero); var malformed=new Context(); register(ref malformed,copy); Check(malformed.Kind==7,"Malformed native target accepted");
            var unsupported=new Context(); Check(Fn<Query>(m,"boom_class_loader_retrieve")(ref unsupported,Array.Empty<ulong>(),pool)==IntPtr.Zero&&unsupported.Kind==20,"Unimplemented directives fabricated a policy");
        } finally {
            Fn<Release>(m,"boom_trace_release")(Fn<Pointer>(m,"boom_get_trace_pool")());
            if(heap!=IntPtr.Zero) Fn<One>(m,"boom_heap_destroy")(heap);
            if(copy!=IntPtr.Zero) Marshal.FreeHGlobal(copy);
            FreeLibrary(m);
        }
    }
    public static void Run(string dll,uint appType,uint appKey,int loaderRow,uint[] loaderIds) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero,node=IntPtr.Zero;
        bool released=false;
        Check(m!=IntPtr.Zero,"Class loader image load failed");
        try {
            var create=Fn<Create>(m,"boom_heap_create"); heap=create(4194304);
            Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Heap bind failed");
            IntPtr pool=Fn<Pointer>(m,"boom_get_class_loader_pool")();
            IntPtr trace=Fn<Pointer>(m,"boom_get_trace_pool")(),mirrors=Marshal.ReadIntPtr(pool,16);
            var mirror=Fn<Mirror>(m,"boom_mirror_load"); var query=Fn<Query>(m,"boom_class_loader_field");
            var entry=Fn<Entry>(m,"boom_entry32"); var bind=Fn<Bind>(m,"boom_class_loader_bind");
            var c=new Context(); IntPtr app=mirror(heap,mirrors,appType,ref c);
            Check(app!=IntPtr.Zero&&c.Kind==0,"Application canonical mirror missing");
            c=new Context(); Check(query(ref c,new[]{Bits(app)},pool)==IntPtr.Zero&&c.Kind==7,"Unbound application loader silently returned null");
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};
            Check(query(ref pending,null,pool)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending context changed");
            c=new Context(); Check(query(ref c,new[]{0UL},pool)==IntPtr.Zero&&c.Kind==4,"Null Class field receiver differs");
            IntPtr rows=Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,24),16),tag=Marshal.ReadIntPtr(rows,loaderRow*40);
            var alloc=Fn<Alloc>(m,"boom_heap_alloc"); IntPtr loader=Storage(alloc,heap,tag),other=Storage(alloc,heap,tag);
            Check(loader!=IntPtr.Zero&&other!=IntPtr.Zero,"VM loader fixture storage allocation failed");
            Check(bind(pool,appKey,IntPtr.Zero)==87&&bind(pool,appKey,app)==87&&bind(pool,0,loader)==87,"Invalid loader identity accepted");
            foreign=create(4096); IntPtr foreignLoader=Storage(alloc,foreign,tag);
            Check(foreignLoader!=IntPtr.Zero&&bind(pool,appKey,foreignLoader)==87,"Foreign heap loader accepted");
            node=Marshal.AllocHGlobal(48); Marshal.Copy(new byte[48],0,node,48);
            var frame=new Context(); Check(Fn<Enter>(m,"boom_trace_enter")(trace,node,Marshal.ReadIntPtr(trace,24),ref frame)==0,"VM fixture frame entry failed");
            try { Check(bind(pool,appKey,loader)==170,"Loader binding raced active execution"); }
            finally { Check(Fn<Leave>(m,"boom_trace_leave")(trace,node,ref frame)==0,"VM fixture frame leave failed"); }
            Check(bind(pool,appKey,loader)==0&&bind(pool,appKey,loader)==0&&bind(pool,appKey,other)==87,"Loader identity binding is not immutable");
            Check(Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,32),checked((int)appKey*8))==loader,"Loader identity is not rooted");
            var canonical=new IntPtr[loaderIds.Length];
            for(uint i=0;i<loaderIds.Length;i++) {
                c=new Context(); canonical[i]=mirror(heap,mirrors,i,ref c); Check(canonical[i]!=IntPtr.Zero&&c.Kind==0,"Canonical mirror failed");
                c=new Context(); Check(mirror(heap,mirrors,i,ref c)==canonical[i]&&c.Kind==0,"Mirror identity changed");
                IntPtr expected=loaderIds[i]==0?IntPtr.Zero:loader;
                c=new Context(); Check(entry(ref c,new[]{Bits(canonical[i])})==expected&&c.Kind==0&&c.Depth==0,"Retained source getter differs at type "+i+" kind="+c.Kind);
            }
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=> {
                for(int j=0;j<512;j++) { int i=(worker*31+j)%canonical.Length; var parallel=new Context(); IntPtr expected=loaderIds[i]==0?IntPtr.Zero:loader;
                    Check(entry(ref parallel,new[]{Bits(canonical[i])})==expected&&parallel.Kind==0&&parallel.Depth==0,"Parallel source getter changed identity"); }
            });
            IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint count);
            var seen=new HashSet<IntPtr>(); var todo=new Stack<IntPtr>(); for(int i=0;i<count;i++) todo.Push(Marshal.ReadIntPtr(statics,i*8));
            while(todo.Count>0) { IntPtr obj=todo.Pop(); if(obj==IntPtr.Zero||!seen.Add(obj))continue; uint refs=(uint)Marshal.ReadInt32(obj,-20); for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(obj,i*8)); }
            Check(seen.Contains(loader)&&!seen.Contains(other),"Loader static root reachability differs");
            Check(Fn<Collect>(m,"boom_heap_collect")(heap,statics,count)!=ulong.MaxValue&&(ulong)Marshal.ReadInt64(heap,56)==(ulong)seen.Count,"Quiescent collection lost loader roots");
            c=new Context(); Check(entry(ref c,new[]{Bits(app)})==loader&&c.Kind==0,"Loader identity changed after collection");
            Check(Fn<Release>(m,"boom_trace_release")(trace)==0,"Source trace close failed"); released=true;
            Check(bind(pool,appKey,loader)==87,"Closed runtime accepted loader binding");
        } finally {
            if(!released) Fn<Release>(m,"boom_trace_release")(Fn<Pointer>(m,"boom_get_trace_pool")());
            if(foreign!=IntPtr.Zero) Fn<One>(m,"boom_heap_destroy")(foreign);
            if(heap!=IntPtr.Zero) Fn<One>(m,"boom_heap_destroy")(heap);
            if(node!=IntPtr.Zero) Marshal.FreeHGlobal(node);
            FreeLibrary(m);
        }
    }
}
