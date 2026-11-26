// Development driver only. Java construction, frames, trace capture, pool and GC execute MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomThrowableProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint c,uint f);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Enter(IntPtr p,IntPtr node,IntPtr method,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Leave(IntPtr p,IntPtr node,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Head(IntPtr p,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint ReleasePool(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Fill(ref Context c,[In] ulong[] a,IntPtr plan);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    sealed class Method {public string Class,Name,File;public int[] PCs,Lines;}
    static readonly Dictionary<uint,Method> methods=new Dictionary<uint,Method>();
    public static void Reset(){methods.Clear();}
    public static void MethodInfo(uint id,string name,string method,string file,int[] pcs,int[] lines){Check(pcs.Length==lines.Length,"Line table length mismatch");methods.Add(id,new Method{Class=name.Replace('/','.'),Name=method,File=file??"null",PCs=pcs,Lines=lines});}
    static void Check(bool ok,string s){if(!ok)throw new Exception(s);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Throwable DLL load failed");return m;}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static IntPtr Row(IntPtr plan,IntPtr value){IntPtr rows=Marshal.ReadIntPtr(plan,16),layout=Marshal.ReadIntPtr(value,-8);int n=Marshal.ReadInt32(plan,8);for(int i=0;i<n;i++){IntPtr row=IntPtr.Add(rows,i*48);if(Marshal.ReadIntPtr(row)==layout)return row;}throw new Exception("Throwable receiver layout not in its source plan");}
    static int Depth(IntPtr row,IntPtr value){int offset=Marshal.ReadInt32(row,12);return Marshal.ReadInt32(row,16)==8?checked((int)Marshal.ReadInt64(value,offset)):Marshal.ReadInt32(value,offset);}
    static string Trace(IntPtr value,IntPtr plan,IntPtr pool){
        Check(value!=IntPtr.Zero,"Original Throwable was not retained");IntPtr row=Row(plan,value),trace=Marshal.ReadIntPtr(value,Marshal.ReadInt32(row,8));int n=Depth(row,value);
        Check(n>=0&&n<=128,"Invalid captured depth");if(trace==IntPtr.Zero){Check(n==0,"Absent trace retained an invalid depth");return "";}
        Check(unchecked((uint)Marshal.ReadInt32(trace,-24))==0xb00b0001U&&Marshal.ReadInt64(trace,-8)==267&&Marshal.ReadInt32(trace,-20)==0&&Marshal.ReadInt64(trace,-16)==(n+2)*8L,"Opaque backtrace is not an owned primitive array");
        Check(Marshal.ReadInt64(trace)==0x142545243L&&Marshal.ReadIntPtr(trace,8)==pool,"Backtrace ABI/module identity mismatch");
        var frames=new List<string>();for(int i=0;i<n;i++){
            ulong record=unchecked((ulong)Marshal.ReadInt64(trace,16+i*8));uint id=(uint)(record>>32),pc=(uint)record;Method m;Check(methods.TryGetValue(id,out m),"Backtrace has an unknown Java method");
            int best=-1,line=-1;for(int j=0;j<m.PCs.Length;j++)if(m.PCs[j]<=pc&&m.PCs[j]>=best){best=m.PCs[j];line=m.Lines[j];}
            frames.Add(m.Class+"#"+m.Name+"#"+m.File+"#"+line);
        }return String.Join("|",frames);
    }
    static void Idle(IntPtr runtime,IntPtr pool){var c=new Context();Check(Marshal.ReadInt64(pool,32)==0&&Fn<Head>(runtime,"boom_trace_head")(pool,ref c)==IntPtr.Zero&&c.Kind==0,"Generated frame chain was not unwound");}
    static int Reachable(IntPtr roots,uint count){
        var live=new HashSet<IntPtr>();var pending=new Stack<IntPtr>();for(int i=0;i<count;i++)pending.Push(Marshal.ReadIntPtr(roots,i*8));
        while(pending.Count!=0){IntPtr value=pending.Pop();if(value==IntPtr.Zero||!live.Add(value))continue;uint flags=unchecked((uint)Marshal.ReadInt32(value,-24)),refs=unchecked((uint)Marshal.ReadInt32(value,-20));long bytes=Marshal.ReadInt64(value,-16);Check((flags&0xfffffffd)==0xb00b0001&&bytes>=0&&refs<=(ulong)bytes/8&&live.Count<=1048576,"Invalid retained exception graph");for(int i=0;i<refs;i++)pending.Push(Marshal.ReadIntPtr(value,i*8));}return live.Count;
    }
    static void GC(IntPtr m,IntPtr h){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);int count=Reachable(roots,n);Check(Fn<Collect>(m,"boom_heap_collect")(h,roots,n)!=ulong.MaxValue&&Marshal.ReadInt64(h,56)==count,"Throwable/static graph was lost or temporary trace storage leaked");}
    static void Close(IntPtr m,IntPtr heap){if(m!=IntPtr.Zero){Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Trace pool still has active Java frames");Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Trace pool shutdown was not idempotent");if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(m);}}
    public static string[] Snapshots(string dll,string runtime,uint owner,uint field,uint[] inputs){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Throwable snapshot heap failed");IntPtr plan=Fn<Pointer>(m,"boom_get_throwable_plan")(),pool=Fn<Pointer>(m,"boom_get_trace_pool")();var entry=Fn<Entry>(m,"boom_entry");string[] result=new string[inputs.Length];
            for(int i=0;i<inputs.Length;i++){var c=new Context();entry(ref c,new ulong[]{inputs[i]});Check(c.Kind==0&&c.Depth==0,"Original Throwable constructor failed: kind="+c.Kind+", method="+c.Method);Idle(r,pool);IntPtr value=Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(owner,field));result[i]=Trace(value,plan,pool);GC(m,heap);Check(result[i]==Trace(value,plan,pool),"Collection changed an immutable captured trace");}
            return result;
        }finally{Close(m,heap);FreeLibrary(r);}
    }
    public static void Parallel(string dll,string runtime){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,workers=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Throwable worker heap failed");IntPtr trace=Fn<Pointer>(m,"boom_get_trace_pool")();Check(Marshal.ReadInt32(trace,8)==0,"Trace TLS initialized before Java execution");
            const int count=2049;long[] args=new long[count*16];for(int i=0;i<count;i++)args[i*16]=unchecked(0x80000000U+(uint)i*65537);
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);workers=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(workers!=IntPtr.Zero,"Throwable workers failed");
            for(int batch=0;batch<3;batch++){Check(Fn<PoolRun>(r,"boom_pool_run")(workers,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Throwable worker batch failed");for(int i=0;i<count;i++){uint n=(uint)args[i*16];uint length=(n&3)==0?4U:(n&3)==1?7U:6U;Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked(n+length+32)&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Throwable/frame state crossed worker records");}Idle(r,trace);GC(m,heap);}
            Check(Marshal.ReadInt32(trace,8)==2,"Trace TLS pool did not publish");
        }finally{if(workers!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(workers);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);Close(m,heap);FreeLibrary(r);}
    }
    public static void TraceOom(string dll,string runtime,uint owner,uint field){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(4096);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Trace OOM heap failed");var entry=Fn<Entry>(m,"boom_entry");var c=new Context();Check(entry(ref c,new ulong[]{0})==6&&c.Kind==0,"Reusable Throwable bootstrap failed");
            IntPtr pool=Fn<Pointer>(m,"boom_get_trace_pool")(),plan=Fn<Pointer>(m,"boom_get_throwable_plan")(),value=Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(owner,field));Trace(value,plan,pool);Idle(r,pool);
            ulong remaining=checked((ulong)(Marshal.ReadInt64(heap,16)-Marshal.ReadInt64(heap,48)));Check(remaining>64&&Fn<Alloc>(r,"boom_heap_alloc")(heap,remaining-32,0,1)!=IntPtr.Zero,"Trace OOM prefill failed");
            c=new Context();Check(entry(ref c,new ulong[]{1})==7&&c.Kind==0&&c.Depth==0,"Stack-trace allocation OOM escaped the original Java fillInStackTrace wrapper");
            IntPtr row=Row(plan,value);Check(Marshal.ReadIntPtr(value,Marshal.ReadInt32(row,8))==IntPtr.Zero&&Depth(row,value)==0&&Marshal.ReadIntPtr(value,Marshal.ReadInt32(row,20))!=IntPtr.Zero,"Trace OOM did not retain the original Java sentinel protocol");Idle(r,pool);GC(m,heap);
            c=new Context();Check(entry(ref c,new ulong[]{2})==8&&c.Kind==0&&c.Depth==0,"Trace allocation did not recover after collection");Check(Trace(value,plan,pool).Length!=0,"Recovered Throwable did not capture real Java frames");Idle(r,pool);GC(m,heap);
        }finally{Close(m,heap);FreeLibrary(r);}
    }
    public static void FrameAbi(string dll,string runtime){
        IntPtr m=Open(dll),r=Open(runtime),pool=Marshal.AllocHGlobal(48),node=Marshal.AllocHGlobal(48),nested=Marshal.AllocHGlobal(48);
        try{IntPtr original=Fn<Pointer>(m,"boom_get_trace_pool")();long[] data=new long[6];Marshal.Copy(original,data,0,6);data[1]=unchecked((long)0xffffffff00000000UL);data[4]=0;data[5]=0;Marshal.Copy(data,0,pool,6);Marshal.Copy(new byte[48],0,node,48);IntPtr method=Marshal.ReadIntPtr(pool,24);var enter=Fn<Enter>(r,"boom_trace_enter");var leave=Fn<Leave>(r,"boom_trace_leave");var head=Fn<Head>(r,"boom_trace_head");var release=Fn<ReleasePool>(r,"boom_trace_release");
            foreach(IntPtr wrong in new[]{IntPtr.Add(method,1),new IntPtr(method.ToInt64()+(1L<<37))}){var c=new Context();Check(enter(pool,node,wrong,ref c)==1&&c.Kind==7&&Marshal.ReadInt64(pool,32)==0,"Invalid Java method pointer entered a frame");}
            var context=new Context();Check(enter(pool,node,method,ref context)==0&&context.Kind==0&&Marshal.ReadInt64(pool,32)==1,"Raw Java frame registration failed");Check(head(pool,ref context)==node&&release(pool)==170,"Live Java frame did not prevent TLS release");
            context.Depth=2;Marshal.Copy(new byte[48],0,nested,48);Check(enter(pool,nested,method,ref context)==0&&Marshal.ReadInt64(pool,32)==1&&Marshal.ReadInt32(nested,28)==0,"Nested Java method contended on the global Context lease");Check(leave(pool,nested,ref context)==0&&Marshal.ReadInt64(pool,32)==1,"Nested frame dropped its parent's lease");
            var other=new Context{Depth=2};Check(enter(pool,nested,method,ref other)==1&&other.Kind==7&&Marshal.ReadInt64(pool,32)==1,"Unrelated Context borrowed another entry's lease");other=new Context();Check(enter(pool,nested,method,ref other)==0&&Marshal.ReadInt64(pool,32)==2,"Nested entry Context did not own its own lease");Check(leave(pool,nested,ref other)==0&&Marshal.ReadInt64(pool,32)==1,"Nested entry Context lease did not unwind");
            context.Kind=3;context.PC=11;context.Method=7;context.Depth=2;Check(leave(pool,node,ref context)==0&&context.Kind==3&&context.PC==11&&context.Method==7&&context.Depth==2,"Unwind overwrote an existing exception origin");Check(Marshal.ReadInt64(pool,32)==0&&release(pool)==0&&release(pool)==0,"Quiescent TLS release failed");context=new Context();Check(enter(pool,node,method,ref context)==1&&context.Kind==7&&Marshal.ReadInt64(pool,32)==0,"Closed TLS pool accepted a new Java frame");
        }finally{Fn<ReleasePool>(r,"boom_trace_release")(pool);Marshal.FreeHGlobal(nested);Marshal.FreeHGlobal(node);Marshal.FreeHGlobal(pool);Close(m,IntPtr.Zero);FreeLibrary(r);}
    }
}
