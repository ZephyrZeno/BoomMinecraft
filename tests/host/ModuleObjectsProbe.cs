// Disposable controller only. Original constructor and VM services execute MASM.
// Loader storage is an explicit preconstructor VM fixture, not a working loader.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomModuleObjectsProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Class(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Query(ref Context c,[In] ulong[] a,IntPtr p,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Index(ref Context c,IntPtr v,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Value(IntPtr v,IntPtr p,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Bind(IntPtr p,uint id,IntPtr v);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr h,IntPtr p,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Publish(ref Context c,[In] ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr LoadModule(ref Context c,IntPtr p,uint index);
    static void Check(bool v,string why) { if(!v) throw new Exception(why); }
    static T Fn<T>(IntPtr m,string n) { IntPtr p=GetProcAddress(m,n); Check(p!=IntPtr.Zero,"Missing "+n); return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static ulong Bits(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    static IntPtr Zero(int size) {IntPtr p=Marshal.AllocHGlobal(size);Marshal.Copy(new byte[size],0,p,size);return p;}
    public static void RunBootstrap(string dll,string runtime) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Bootstrap Module images");
        var temporary=new List<IntPtr>();
        try {
            heap=Fn<Create>(m,"boom_heap_create")(4194304);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Bootstrap Module heap");
            IntPtr original=Fn<Pointer>(m,"boom_get_module_pool")();int count=Marshal.ReadInt32(original,12);
            IntPtr pool=Zero(144),roots=Zero((count+1)*8),rows=Zero((count+1)*8),keys=Zero((count+1)*4),owner=Zero(64),javaCell=Zero(8),binding=Zero(48);
            temporary.AddRange(new[]{pool,roots,rows,keys,owner,javaCell,binding});
            byte[] copy=new byte[144];Marshal.Copy(original,copy,0,144);Marshal.Copy(copy,0,pool,144);
            copy=new byte[count*8];Marshal.Copy(Marshal.ReadIntPtr(original,24),copy,0,copy.Length);Marshal.Copy(copy,0,rows,copy.Length);
            copy=new byte[count*4];Marshal.Copy(Marshal.ReadIntPtr(original,104),copy,0,copy.Length);Marshal.Copy(copy,0,keys,copy.Length);
            Marshal.WriteInt32(pool,12,count+1);Marshal.WriteIntPtr(pool,16,roots);Marshal.WriteIntPtr(pool,24,rows);Marshal.WriteIntPtr(pool,104,keys);
            // No layer is queried by this isolated unnamed-module fixture. An
            // original layer pool points back to the original Module pool.
            Marshal.WriteIntPtr(pool,80,IntPtr.Zero);
            Marshal.WriteInt32(rows,count*8,-1);Marshal.WriteInt32(keys,count*4,0);
            IntPtr vmCell=IntPtr.Add(roots,count*8);
            // Explicit metadata fixture: original BootLoader.<clinit> is not run.
            Marshal.WriteInt32(owner,0,0x434c4153);Marshal.WriteInt32(owner,4,2);
            Marshal.WriteInt32(binding,0,0x444d5542);Marshal.WriteInt32(binding,4,1);
            Marshal.WriteIntPtr(binding,16,owner);Marshal.WriteIntPtr(binding,24,javaCell);Marshal.WriteIntPtr(binding,32,pool);Marshal.WriteIntPtr(binding,40,vmCell);
            var entry=Fn<Entry>(m,"boom_entry32");var publish=Fn<Publish>(r,"boom_boot_unnamed_publish");
            var c=new Context();IntPtr module=entry(ref c,new[]{0UL});Check(module!=IntPtr.Zero&&c.Kind==0,"Original bootstrap Module constructor");
            Marshal.WriteIntPtr(javaCell,module);ulong[] args={Bits(module)};
            c=new Context();Check(Fn<Value>(r,"boom_module_objects_value")(module,pool,ref c)==module&&c.Kind==0,"Bootstrap fixture physical Module validation: "+c.Kind);
            c=new Context();publish(ref c,args,binding);Check(c.Kind==7&&Marshal.ReadIntPtr(vmCell)==IntPtr.Zero,"Uninitialized BootLoader accepted");
            Marshal.WriteInt32(owner,8,1);Marshal.WriteInt32(owner,12,unchecked((int)GetCurrentThreadId()+1));
            c=new Context();publish(ref c,args,binding);Check(c.Kind==7,"Wrong BootLoader initialization owner accepted");
            Marshal.WriteInt32(owner,12,unchecked((int)GetCurrentThreadId()));
            c=new Context();publish(ref c,args,binding);Check(c.Kind==0&&Marshal.ReadIntPtr(vmCell)==module&&Marshal.ReadInt32(binding,8)==2,"Owner bootstrap Module publication: kind="+c.Kind+" root="+Marshal.ReadIntPtr(vmCell)+" key="+Marshal.ReadInt32(keys,count*4));
            Marshal.WriteInt32(owner,8,2);Marshal.WriteInt32(binding,8,0);Marshal.WriteIntPtr(vmCell,IntPtr.Zero);
            System.Threading.Tasks.Parallel.For(0,8,worker=>{for(int i=0;i<128;i++){var local=new Context();publish(ref local,args,binding);Check(local.Kind==0,"Concurrent bootstrap Module publication");}});
            Check(Marshal.ReadIntPtr(vmCell)==module&&Marshal.ReadInt32(binding,8)==2,"Canonical bootstrap root split");
            c=new Context();Check(Fn<LoadModule>(r,"boom_module_load")(ref c,pool,(uint)count)==module&&c.Kind==0,"Bootstrap unnamed canonical load");
            c=new Context();Check(Fn<Index>(r,"boom_module_index")(ref c,module,pool)==count&&c.Kind==0,"Bootstrap unnamed canonical index");
            foreach(int offset in new[]{0,4,8,12}) {int old=Marshal.ReadInt32(binding,offset);Marshal.WriteInt32(binding,offset,-1);c=new Context();publish(ref c,args,binding);Check(c.Kind==7,"Malformed bootstrap binding "+offset);Marshal.WriteInt32(binding,offset,old);}
            int name=Marshal.ReadInt32(pool,112),loader=Marshal.ReadInt32(pool,116);
            foreach(int offset in new[]{name,loader}){Marshal.WriteIntPtr(module,offset,module);c=new Context();publish(ref c,args,binding);Check(c.Kind==7,"Named/application Module accepted");Marshal.WriteIntPtr(module,offset,IntPtr.Zero);}
            Marshal.WriteIntPtr(binding,40,roots);c=new Context();publish(ref c,args,binding);Check(c.Kind==7,"Named root overwritten");Marshal.WriteIntPtr(binding,40,vmCell);
            Marshal.WriteIntPtr(binding,40,IntPtr.Add(roots,(count+1)*8));c=new Context();publish(ref c,args,binding);Check(c.Kind==7,"Out-of-bounds root accepted");Marshal.WriteIntPtr(binding,40,vmCell);
            c=new Context();IntPtr second=entry(ref c,new[]{0UL});Check(second!=IntPtr.Zero&&c.Kind==0,"Second original Module constructor");
            Marshal.WriteIntPtr(javaCell,second);c=new Context();publish(ref c,new[]{Bits(second)},binding);Check(c.Kind==7&&Marshal.ReadIntPtr(vmCell)==module,"Canonical VM root overwritten");
            Marshal.WriteIntPtr(javaCell,IntPtr.Zero);c=new Context();publish(ref c,args,binding);Check(c.Kind==7,"Java snapshot mismatch accepted");
            var pending=new Context{Kind=16,PC=3,Method=5,Depth=2,Pending=7,Plan=11};publish(ref pending,null,IntPtr.Zero);Check(pending.Kind==16&&pending.PC==3&&pending.Method==5&&pending.Depth==2&&pending.Pending==7&&pending.Plan==11,"Bootstrap pending context changed");
            // Collect with both the compiled image roots and the explicit VM-root
            // fixture. Java's private source cell has been cleared deliberately.
            IntPtr sourceRoots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);IntPtr combined=Zero(checked((int)(n+1)*8));temporary.Add(combined);
            for(int i=0;i<n;i++)Marshal.WriteIntPtr(combined,i*8,Marshal.ReadIntPtr(sourceRoots,i*8));Marshal.WriteIntPtr(combined,(int)n*8,Marshal.ReadIntPtr(vmCell));
            if(GetProcAddress(m,"boom_release_trace_pool")!=IntPtr.Zero)Fn<Release>(m,"boom_release_trace_pool")(IntPtr.Zero);
            Fn<Collect>(m,"boom_heap_collect")(heap,combined,n+1);
            c=new Context();Check(Fn<LoadModule>(r,"boom_module_load")(ref c,pool,(uint)count)==module&&c.Kind==0,"Bootstrap VM root lost after collection");
        } finally {
            if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);
            foreach(IntPtr p in temporary)Marshal.FreeHGlobal(p);
            if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);
        }
    }
    public static void Run(string dll,uint classID,uint appType,uint baseType,uint appKey,int loaderRow) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero;
        Check(m!=IntPtr.Zero,"Physical Module image load failed");
        try {
            var create=Fn<Create>(m,"boom_heap_create"); heap=create(4194304);
            Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Heap bind failed");
            IntPtr pool=Fn<Pointer>(m,"boom_get_module_pool")(),loaderPool=Fn<Pointer>(m,"boom_get_class_loader_pool")();
            IntPtr state=Fn<Class>(m,"boom_get_class_descriptor")(classID),layout=Marshal.ReadIntPtr(pool,32);
            Check(Marshal.ReadInt32(pool,4)==3&&Marshal.ReadIntPtr(pool,96)==loaderPool,"Module physical pool differs");
            int name=Marshal.ReadInt32(pool,112),loaderField=Marshal.ReadInt32(pool,116),layer=Marshal.ReadInt32(pool,120),unnamed=Marshal.ReadInt32(pool,124),descriptor=Marshal.ReadInt32(pool,128);
            var entry=Fn<Entry>(m,"boom_entry32"); var query=Fn<Query>(m,"boom_module_intrinsic");
            var layers=Fn<Query>(m,"boom_layer_intrinsic"); var value=Fn<Value>(m,"boom_module_objects_value");
            Check(state!=IntPtr.Zero&&Marshal.ReadInt32(state,8)==0,"Module initialized before VM construction");
            var c=new Context(); IntPtr empty=entry(ref c,new[]{0UL});
            Check(empty!=IntPtr.Zero&&c.Kind==0&&c.Depth==0&&Marshal.ReadInt32(state,8)==0,"Original preinitialization constructor failed: "+c.Kind);
            Check(Marshal.ReadIntPtr(empty,-8)==layout&&Marshal.ReadInt64(empty,-16)==Marshal.ReadInt64(layout,8)&&Marshal.ReadInt32(empty,-20)==Marshal.ReadInt32(layout,16),"Constructor used an opaque/foreign layout");
            foreach(int off in new[]{name,loaderField,layer,descriptor}) Check(Marshal.ReadIntPtr(empty,off)==IntPtr.Zero,"Original null constructor field differs");
            c=new Context(); Check(query(ref c,new[]{Bits(empty)},pool,1)==IntPtr.Zero&&c.Kind==0,"Physical getName differs");
            c=new Context(); Check(query(ref c,new[]{Bits(empty)},pool,2)==IntPtr.Zero&&c.Kind==0,"Physical isNamed differs");
            c=new Context(); Check(layers(ref c,new[]{Bits(empty)},pool,3)==IntPtr.Zero&&c.Kind==0,"Unregistered unnamed Module should have null layer");
            c=new Context(); Check(Fn<Index>(m,"boom_module_index")(ref c,empty,pool)==-1&&c.Kind==7,"Unregistered object was assigned an invented canonical index");
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};
            Check(query(ref pending,null,pool,0)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending module context changed");
            c=new Context(); Check(value(IntPtr.Zero,pool,ref c)==IntPtr.Zero&&c.Kind==4,"Null Module accepted");
            Marshal.WriteInt32(state,8,2); c=new Context(); Check(entry(ref c,new[]{0UL})==IntPtr.Zero&&c.Kind==16&&c.Pending!=0,"VM preinitialization rejection did not materialize a Throwable: "+c.Kind); Marshal.WriteInt32(state,8,0);
            var mirror=Fn<Mirror>(m,"boom_mirror_load"); IntPtr mirrors=Marshal.ReadIntPtr(pool,56);
            c=new Context(); IntPtr app=mirror(heap,mirrors,appType,ref c); Check(app!=IntPtr.Zero&&c.Kind==0,"App mirror missing");
            c=new Context(); Check(query(ref c,new[]{Bits(app)},pool,0)==IntPtr.Zero&&c.Kind==7,"Unbound application module was fabricated");
            var alloc=Fn<Alloc>(m,"boom_heap_alloc"); IntPtr rows=Marshal.ReadIntPtr(Marshal.ReadIntPtr(loaderPool,24),16),loaderTag=Marshal.ReadIntPtr(rows,loaderRow*40);
            IntPtr loader=alloc(heap,(ulong)Marshal.ReadInt64(loaderTag,8),(uint)Marshal.ReadInt32(loaderTag,16),loaderTag);
            Check(loader!=IntPtr.Zero,"Preconstructor loader fixture allocation failed");
            c=new Context(); Check(value(loader,pool,ref c)==IntPtr.Zero&&c.Kind==7,"Wrong object tag accepted as Module");
            c=new Context(); IntPtr module=entry(ref c,new[]{Bits(loader)});
            Check(module!=IntPtr.Zero&&c.Kind==0&&Marshal.ReadIntPtr(module,loaderField)==loader,"Original Java constructor did not store actual loader");
            Marshal.WriteIntPtr(loader,unnamed,module);
            Check(Fn<Bind>(m,"boom_class_loader_bind")(loaderPool,appKey,loader)==0,"Loader fixture bind failed");
            c=new Context(); Check(query(ref c,new[]{Bits(app)},pool,0)==module&&c.Kind==0,"Class.getModule duplicated original constructed unnamed Module");
            c=new Context(); IntPtr baseMirror=mirror(heap,mirrors,baseType,ref c); Check(baseMirror!=IntPtr.Zero&&c.Kind==0,"Base mirror missing");
            IntPtr baseModule=IntPtr.Zero;
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=> {
                for(int j=0;j<128;j++) {
                    var parallel=new Context(); Check(query(ref parallel,new[]{Bits(app)},pool,0)==module&&parallel.Kind==0,"Concurrent app Module identity changed");
                    parallel=new Context(); IntPtr current=query(ref parallel,new[]{Bits(baseMirror)},pool,0);
                    Check(current!=IntPtr.Zero&&parallel.Kind==0,"Concurrent canonical base Module failed");
                    System.Threading.Interlocked.CompareExchange(ref baseModule,current,IntPtr.Zero);
                    Check(current==baseModule,"Concurrent base Module identity split");
                    parallel=new Context(); IntPtr constructed=entry(ref parallel,new[]{Bits(loader)});
                    Check(constructed!=IntPtr.Zero&&parallel.Kind==0&&parallel.Depth==0&&Marshal.ReadIntPtr(constructed,loaderField)==loader,"Concurrent original constructor failed");
                }
            });
            Check(Marshal.ReadIntPtr(baseModule,-8)==layout&&Marshal.ReadIntPtr(baseModule,name)!=IntPtr.Zero&&Marshal.ReadIntPtr(baseModule,loaderField)==IntPtr.Zero,"Base module physical fields differ");
            c=new Context(); Check(query(ref c,new[]{Bits(baseModule)},pool,1)==Marshal.ReadIntPtr(baseModule,name)&&c.Kind==0,"Named getter did not read actual Java field");
            c=new Context(); Check(query(ref c,new[]{Bits(baseModule)},pool,2).ToInt64()==1&&c.Kind==0,"Named flag differs");
            c=new Context(); IntPtr boot=layers(ref c,null,pool,4); Check(boot!=IntPtr.Zero&&c.Kind==0&&Marshal.ReadIntPtr(baseModule,layer)==boot,"Physical boot layer was not stored");
            c=new Context(); Check(layers(ref c,new[]{Bits(baseModule)},pool,3)==boot&&c.Kind==0,"Physical getLayer differs");
            foreign=create(4096); IntPtr foreignModule=alloc(foreign,(ulong)Marshal.ReadInt64(layout,8),(uint)Marshal.ReadInt32(layout,16),layout);
            c=new Context(); Check(value(foreignModule,pool,ref c)==IntPtr.Zero&&c.Kind==7,"Foreign heap Module accepted");
            IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint count);
            var seen=new HashSet<IntPtr>(); var todo=new Stack<IntPtr>(); for(int i=0;i<count;i++)todo.Push(Marshal.ReadIntPtr(statics,i*8));
            while(todo.Count>0) { IntPtr obj=todo.Pop(); if(obj==IntPtr.Zero||!seen.Add(obj))continue; int refs=Marshal.ReadInt32(obj,-20); for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(obj,i*8)); }
            Check(seen.Contains(loader)&&seen.Contains(module)&&seen.Contains(baseModule)&&seen.Contains(boot)&&!seen.Contains(empty),"Module/loader reference-cycle root graph differs");
            Check(Fn<Collect>(m,"boom_heap_collect")(heap,statics,count)!=ulong.MaxValue&&(ulong)Marshal.ReadInt64(heap,56)==(ulong)seen.Count,"Explicit collection lost physical roots");
            c=new Context(); Check(query(ref c,new[]{Bits(app)},pool,0)==module&&c.Kind==0&&Marshal.ReadIntPtr(module,loaderField)==loader,"Module identity lost after collection");
        } finally {
            Fn<Release>(m,"boom_trace_release")(Fn<Pointer>(m,"boom_get_trace_pool")());
            if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);
            if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);
            FreeLibrary(m);
        }
    }
}
