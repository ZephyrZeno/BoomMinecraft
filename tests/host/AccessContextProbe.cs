// Test controller only. Native security services execute assembly. Synthetic VM
// frames/storage exercise the VM protocol; they are not executed Java methods.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomAccessContextProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Query(ref Context c,[In] ulong[] a,IntPtr p,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Bind(IntPtr p,uint id,IntPtr pd);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Enter(IntPtr p,IntPtr n,IntPtr m,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Leave(IntPtr p,IntPtr n,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint ReleasePool(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr h,IntPtr p,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Registry(IntPtr h,uint max);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Attach(IntPtr r,IntPtr t,uint main);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Block(int n){IntPtr p=Marshal.AllocHGlobal(n);Marshal.Copy(new byte[n],0,p,n);return p;}
    static IntPtr Copy(IntPtr p,int n){IntPtr q=Block(n);byte[] b=new byte[n];Marshal.Copy(p,b,0,n);Marshal.Copy(b,0,q,n);return q;}
    static IntPtr Object(Alloc alloc,IntPtr heap,IntPtr layout){return alloc(heap,(ulong)Marshal.ReadInt64(layout,8),(uint)Marshal.ReadInt32(layout,16),layout);}
    static IntPtr Capture(Query query,IntPtr pool,int expected,IntPtr[] domains,bool privileged,IntPtr previous){
        var c=new Context();IntPtr value=query(ref c,Array.Empty<ulong>(),pool,0);Check(c.Kind==expected,"Capture kind="+c.Kind+" expected="+expected);
        if(expected!=0)return IntPtr.Zero;
        if(domains.Length==0&&privileged&&previous==IntPtr.Zero){Check(value==IntPtr.Zero,"Empty privileged capture must be null");return value;}
        Check(value!=IntPtr.Zero,"Missing VM ACC");int context=Marshal.ReadInt32(pool,96),priv=Marshal.ReadInt32(pool,100),flag=Marshal.ReadInt32(pool,104),auth=Marshal.ReadInt32(pool,108);
        Check(Marshal.ReadByte(value,flag)==(privileged?1:0)&&Marshal.ReadByte(value,auth)==1&&Marshal.ReadIntPtr(value,priv)==previous,"VM ACC flags/inherited identity differ");
        IntPtr array=Marshal.ReadIntPtr(value,context);if(domains.Length==0)Check(array==IntPtr.Zero,"Empty domain array must be null");else{Check(array!=IntPtr.Zero&&Marshal.ReadInt64(array,-16)==domains.Length*8&&Marshal.ReadInt32(array,-20)==domains.Length,"Domain array shape differs");for(int i=0;i<domains.Length;i++)Check(Marshal.ReadIntPtr(array,i*8)==domains[i],"Domain order/identity differs at "+i);}
        return value;
    }
    // Domain IDs are real application metadata. Method rows below are explicit VM fixtures.
    public static void Run(string dll,uint appA,uint appB,uint threadClass,int pdRow){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,reg=IntPtr.Zero;bool attached=false;
        var blocks=new List<IntPtr>();IntPtr rawTrace=IntPtr.Zero;
        Check(m!=IntPtr.Zero,"Access context image load failed");
        try{
            heap=Fn<Create>(m,"boom_heap_create")(4194304);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Access context heap bind failed");
            IntPtr pool=Fn<Pointer>(m,"boom_get_access_context_pool")();var query=Fn<Query>(m,"boom_access_context_query");var bind=Fn<Bind>(m,"boom_access_bind_domain");
            var c=new Context();IntPtr first=Fn<Entry>(m,"boom_entry32")(ref c,Array.Empty<ulong>());Check(c.Kind==0&&first!=IntPtr.Zero&&c.Depth==0,"Native entry/class initialization failed: kind="+c.Kind);
            Capture(query,pool,0,Array.Empty<IntPtr>(),false,IntPtr.Zero);
            var concurrentEntry=Fn<Entry>(m,"boom_entry32");
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{
                for(int i=0;i<64;i++){var concurrentContext=new Context();IntPtr value=concurrentEntry(ref concurrentContext,Array.Empty<ulong>());Check(value!=IntPtr.Zero&&concurrentContext.Kind==0&&concurrentContext.Depth==0,"Concurrent source entry/capture failed");}
            });
            IntPtr map=Marshal.ReadIntPtr(pool,24),rows=Marshal.ReadIntPtr(map,16),pdTag=Marshal.ReadIntPtr(rows,pdRow*40);var alloc=Fn<Alloc>(m,"boom_heap_alloc");
            IntPtr pdA=Object(alloc,heap,pdTag),pdB=Object(alloc,heap,pdTag);Check(pdA!=IntPtr.Zero&&pdB!=IntPtr.Zero,"VM PD storage allocation failed");
            Check(bind(pool,appA,IntPtr.Zero)==87&&bind(pool,appA,first)==87,"Invalid initial domain accepted");
            Check(bind(pool,appA,pdA)==0&&bind(pool,appA,pdA)==0&&bind(pool,appA,pdB)==87,"Domain binding must be immutable");
            IntPtr roots=Marshal.ReadIntPtr(pool,120);Check(Marshal.ReadIntPtr(roots,checked((int)appA*8))==pdA,"Bound domain is not rooted");
            var missing=new Context();Check(query(ref missing,Array.Empty<ulong>(),pool,1)==IntPtr.Zero&&missing.Kind==7,"Unattached inherited query accepted");
            reg=Fn<Registry>(m,"boom_threads_create")(heap,32);Check(reg!=IntPtr.Zero&&Fn<One>(m,"boom_bind_thread_registry")(reg)==0,"Registry bind failed");
            IntPtr thread=Object(alloc,heap,Fn<Layout>(m,"boom_get_object_layout")(threadClass));Check(Fn<Attach>(m,"boom_threads_attach")(reg,thread,1)!=IntPtr.Zero,"VM Thread storage attachment failed");attached=true;
            int inherited=Marshal.ReadInt32(pool,112);var inheritedContext=new Context();Check(query(ref inheritedContext,Array.Empty<ulong>(),pool,1)==IntPtr.Zero&&inheritedContext.Kind==0,"Null inherited context differs");
            Marshal.WriteIntPtr(thread,inherited,first);inheritedContext=new Context();Check(query(ref inheritedContext,Array.Empty<ulong>(),pool,1)==first&&inheritedContext.Kind==0,"Inherited context identity differs");
            Marshal.WriteIntPtr(thread,inherited,pdA);inheritedContext=new Context();Check(query(ref inheritedContext,Array.Empty<ulong>(),pool,1)==IntPtr.Zero&&inheritedContext.Kind==7,"Wrong inherited type accepted");Marshal.WriteIntPtr(thread,inherited,first);
            foreach(ulong arg in new[]{0UL,unchecked((ulong)first.ToInt64())}){var escape=new Context();Check(query(ref escape,new[]{arg},pool,2)==IntPtr.Zero&&escape.Kind==0,"Valid native escape failed");}
            IntPtr foreign=Block(32);blocks.Add(foreign);var invalidEscape=new Context();Check(query(ref invalidEscape,new[]{unchecked((ulong)foreign.ToInt64())},pool,2)==IntPtr.Zero&&invalidEscape.Kind==7,"Foreign escape object accepted");
            // A,A,bootstrap,A,B,B,A collapses to A,B,A. Build a separate fixture
            // trace pool; immutable production method tables remain untouched.
            IntPtr fixturePool=Copy(pool,192);blocks.Add(fixturePool);rawTrace=Copy(Marshal.ReadIntPtr(pool,40),48);blocks.Add(rawTrace);
            Marshal.WriteInt32(rawTrace,8,0);Marshal.WriteInt32(rawTrace,12,-1);Marshal.WriteInt64(rawTrace,32,0);Marshal.WriteInt64(rawTrace,40,0);
            const int count=7;IntPtr methods=Block(count*32),extras=Block(count*32),nodes=Block(count*128);blocks.Add(methods);blocks.Add(extras);blocks.Add(nodes);
            Marshal.WriteInt32(rawTrace,16,count);Marshal.WriteIntPtr(rawTrace,24,methods);Marshal.WriteIntPtr(fixturePool,40,rawTrace);Marshal.WriteIntPtr(fixturePool,136,extras);Marshal.WriteInt32(fixturePool,144,count);
            uint bootstrap=0;uint[] ids={appA,appA,bootstrap,appA,appB,appB,appA};
            IntPtr fallbackType=Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,80),16);if(fallbackType==IntPtr.Zero)fallbackType=Marshal.ReadIntPtr(pool,80);
            for(int i=0;i<count;i++){IntPtr row=IntPtr.Add(methods,i*32),extra=IntPtr.Add(extras,i*32);Marshal.WriteInt32(row,i);Marshal.WriteIntPtr(row,8,fallbackType);Marshal.WriteInt32(row,16,1);Marshal.WriteIntPtr(extra,row);Marshal.WriteInt32(extra,8,(int)ids[i]);Marshal.WriteInt32(extra,16,-24);Marshal.WriteInt32(extra,20,3);}
            var enter=Fn<Enter>(m,"boom_trace_enter");var leave=Fn<Leave>(m,"boom_trace_leave");var frameContext=new Context();int entered=0;
            try{
                for(int i=count-1;i>=0;i--){frameContext.Depth=entered==0?0U:2U;Check(enter(rawTrace,IntPtr.Add(nodes,i*128+32),IntPtr.Add(methods,i*32),ref frameContext)==0,"VM fixture enter failed");entered++;}
                Capture(query,fixturePool,7,Array.Empty<IntPtr>(),false,IntPtr.Zero); // B is still unbound.
                Check(bind(fixturePool,appB,pdB)==170,"Binding raced an active Java lease");
            }finally{frameContext.Kind=0;for(int i=count-entered;i<count;i++)Check(leave(rawTrace,IntPtr.Add(nodes,i*128+32),ref frameContext)==0,"VM fixture leave failed");}
            Check(bind(pool,appB,pdB)==0,"Second VM domain binding failed");
            // Re-enter to exercise ordering and privileged caller stopping.
            frameContext=new Context();entered=0;
            try{
                for(int i=count-1;i>=0;i--){frameContext.Depth=entered==0?0U:2U;Check(enter(rawTrace,IntPtr.Add(nodes,i*128+32),IntPtr.Add(methods,i*32),ref frameContext)==0,"VM fixture re-enter failed");entered++;}
                Capture(query,fixturePool,0,new[]{pdA,pdB,pdA},false,IntPtr.Zero);
                var mirrorContext=new Context();IntPtr caller=Fn<Mirror>(m,"boom_mirror_load")(heap,Marshal.ReadIntPtr(pool,32),appB,ref mirrorContext);Check(caller!=IntPtr.Zero&&mirrorContext.Kind==0,"Caller mirror failed");
                var callerContext=new Context();Check(query(ref callerContext,Array.Empty<ulong>(),fixturePool,3)==IntPtr.Zero&&callerContext.Kind==23,"Caller-sensitive annotation was not required");
                Marshal.WriteInt32(extras,12,2);for(int i=1;i<4;i++)Marshal.WriteInt32(extras,i*32+12,4);
                callerContext=new Context();Check(query(ref callerContext,Array.Empty<ulong>(),fixturePool,3)==caller&&callerContext.Kind==0,"Caller class did not skip reflection/adapter frames");
                for(int i=1;i<count;i++)Marshal.WriteInt32(extras,i*32+12,4);callerContext=new Context();Check(query(ref callerContext,Array.Empty<ulong>(),fixturePool,3)==IntPtr.Zero&&callerContext.Kind==0,"Missing caller must be null");
                for(int i=0;i<count;i++)Marshal.WriteInt32(extras,i*32+12,0);
                Marshal.WriteInt32(extras,3*32+12,1);IntPtr locals=IntPtr.Add(nodes,3*128+8);Marshal.WriteIntPtr(locals,8,first);Marshal.WriteIntPtr(locals,16,caller);
                Capture(query,fixturePool,0,new[]{pdA,pdB},true,first);
                Marshal.WriteInt32(extras,12,1);locals=IntPtr.Add(nodes,8);Marshal.WriteIntPtr(locals,8,IntPtr.Zero);mirrorContext=new Context();IntPtr bootCaller=Fn<Mirror>(m,"boom_mirror_load")(heap,Marshal.ReadIntPtr(pool,32),bootstrap,ref mirrorContext);Check(bootCaller!=IntPtr.Zero&&mirrorContext.Kind==0,"Bootstrap caller mirror failed");Marshal.WriteIntPtr(locals,16,bootCaller);
                Capture(query,fixturePool,0,Array.Empty<IntPtr>(),true,IntPtr.Zero);
                Marshal.WriteIntPtr(locals,8,first);Capture(query,fixturePool,0,Array.Empty<IntPtr>(),true,first);
            }finally{frameContext.Kind=0;for(int i=count-entered;i<count;i++)Check(leave(rawTrace,IntPtr.Add(nodes,i*128+32),ref frameContext)==0,"VM fixture final leave failed");}
            Check(Fn<One>(m,"boom_threads_detach")(reg)==0,"VM fixture detach failed");attached=false;
            // Domain roots survive quiescent collection, independently traverse all static roots.
            IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint n);var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>();for(int i=0;i<n;i++)todo.Push(Marshal.ReadIntPtr(statics,i*8));while(todo.Count>0){IntPtr obj=todo.Pop();if(obj==IntPtr.Zero||!seen.Add(obj))continue;uint refs=(uint)Marshal.ReadInt32(obj,-20);for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(obj,i*8));}
            Check(Fn<Collect>(m,"boom_heap_collect")(heap,statics,n)!=ulong.MaxValue&&(ulong)Marshal.ReadInt64(heap,56)==(ulong)seen.Count&&seen.Contains(pdA)&&seen.Contains(pdB),"Domain static roots failed collection");
        }finally{
            if(rawTrace!=IntPtr.Zero)Check(Fn<ReleasePool>(m,"boom_trace_release")(rawTrace)==0,"Fixture trace release failed");
            if(attached)Fn<One>(m,"boom_threads_detach")(reg);if(reg!=IntPtr.Zero){Fn<One>(m,"boom_bind_thread_registry")(IntPtr.Zero);Check(Fn<One>(m,"boom_threads_destroy")(reg)==0,"Registry destroy failed");}
            if(m!=IntPtr.Zero){Check(Fn<ReleasePool>(m,"boom_trace_release")(Fn<Pointer>(m,"boom_get_trace_pool")())==0,"Source trace release failed");if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);FreeLibrary(m);}foreach(IntPtr p in blocks)Marshal.FreeHGlobal(p);
        }
    }
}
