// Development host only. Guest methods, exception factories, monitors and GC are MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomUnwindProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context32 { public uint Kind,PC,Method,Depth; public IntPtr Pending,VM; }
    [StructLayout(LayoutKind.Sequential)] struct BridgeGuard { public uint Kind,PC,Method,CSR; public ulong Guard0,Guard1; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint c,uint f);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry32(ref Context32 c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry16(ref BridgeGuard c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Invoke(IntPtr fn,ref BridgeGuard c,[In] ulong[] a,uint csr);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static void Check(bool ok,string s){if(!ok)throw new Exception(s);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Unwind DLL load failed");return m;}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static BridgeGuard Guard(){return new BridgeGuard{Guard0=0x7341fc092ac6b883UL,Guard1=0x9235a071d3e64209UL};}
    static void CheckGuard(BridgeGuard c){Check(c.Guard0==0x7341fc092ac6b883UL&&c.Guard1==0x9235a071d3e64209UL,"Legacy Context16 bridge overwrote the caller's tail");}
    static int Reachable(IntPtr roots,uint n){
        var seen=new HashSet<IntPtr>();var pending=new Stack<IntPtr>();for(int i=0;i<n;i++)pending.Push(Marshal.ReadIntPtr(roots,i*8));
        while(pending.Count!=0){IntPtr v=pending.Pop();if(v==IntPtr.Zero||!seen.Add(v))continue;uint flags=unchecked((uint)Marshal.ReadInt32(v,-24)),refs=unchecked((uint)Marshal.ReadInt32(v,-20));long bytes=Marshal.ReadInt64(v,-16);Check((flags&0xfffffffd)==0xb00b0001&&bytes>=0&&refs<=(ulong)bytes/8&&seen.Count<1048576,"Invalid exception root graph");for(int i=0;i<refs;i++)pending.Push(Marshal.ReadIntPtr(v,i*8));}return seen.Count;
    }
    static void GC(IntPtr m,IntPtr heap,IntPtr extra){
        IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+1)*8));
        try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));Marshal.WriteIntPtr(all,(int)n*8,extra);int live=Reachable(all,n+1);Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,n+1)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==live,"Exception/static root graph lost or temporary graph leaked");}
        finally{Marshal.FreeHGlobal(all);}
    }
    static void Idle(IntPtr m,IntPtr heap){IntPtr p=Fn<Pointer>(m,"boom_get_trace_pool")();Check(Marshal.ReadInt64(p,32)==0&&Marshal.ReadInt64(heap,112)==0,"Exception unwind leaked Java frames or held monitors");}
    static void Close(IntPtr m,IntPtr heap){if(m!=IntPtr.Zero){Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Active Java frames at shutdown");if(heap!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(heap)!=0,"Unwind heap destroy failed");FreeLibrary(m);}}
    public static string[] Run(string dll,string fpProbe,uint[] inputs){
        IntPtr m=Open(dll),f=Open(fpProbe),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Unwind heap bind failed");var entry=Fn<Entry32>(m,"boom_entry32");var invoke=Fn<Invoke>(f,"boom_probe_numeric");IntPtr bridge=GetProcAddress(m,"boom_entry"),vm=Fn<Pointer>(m,"boom_get_exception_vm")();var result=new List<string>();
            foreach(uint input in inputs){var c=new Context32();ulong v=entry(ref c,new ulong[]{input});Check(c.Kind==0&&c.Pending==IntPtr.Zero&&c.Depth==0&&c.VM==vm,"Context32 guest failed: kind="+c.Kind+", method="+c.Method+", pc="+c.PC);result.Add("v "+(v&0xffffffff).ToString("x16"));Idle(m,heap);GC(m,heap,IntPtr.Zero);
                foreach(uint csr in new uint[]{0x1f80,0xffc0}){var g=Guard();v=invoke(bridge,ref g,new ulong[]{input},csr);CheckGuard(g);Check(g.Kind==0&&g.CSR==csr,"Context16 bridge failed or lost caller MXCSR: kind="+g.Kind+", method="+g.Method+", pc="+g.PC);result.Add("v "+(v&0xffffffff).ToString("x16"));Idle(m,heap);GC(m,heap,IntPtr.Zero);}
            }return result.ToArray();
        }finally{Close(m,heap);FreeLibrary(f);}
    }
    public static void Uncaught(string dll,uint childClass){
        IntPtr m=Open(dll),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Uncaught heap bind failed");var c=new Context32();ulong v=Fn<Entry32>(m,"boom_entry32")(ref c,new ulong[]{0});Check(v==0&&c.Kind==16&&c.Pending!=IntPtr.Zero&&c.Depth==0,"Uncaught pending object was lost");IntPtr layout=Marshal.ReadIntPtr(c.Pending,-8);Check(layout==Fn<Layout>(m,"boom_get_object_layout")(childClass),"Uncaught exception type changed");Idle(m,heap);GC(m,heap,c.Pending);Check(Marshal.ReadIntPtr(c.Pending,-8)==layout,"External pending exception did not survive explicit rooting");var g=Guard();v=Fn<Entry16>(m,"boom_entry")(ref g,new ulong[]{0});CheckGuard(g);Check(g.Kind==16&&v!=0,"Context16 bridge did not return the uncaught object in RAX");GC(m,heap,new IntPtr(unchecked((long)v)));Idle(m,heap);
        }finally{Close(m,heap);}
    }
    public static void Parallel(string dll,string runtime){
        ParallelBoth(dll,runtime,false);
    }
    public static void ParallelFailure(string dll,string runtime){
        ParallelBoth(dll,runtime,true);
    }
    static void ParallelBoth(string dll,string runtime,bool failure){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;const int n=6147;
        try{heap=Fn<Create>(m,"boom_heap_create")(32*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Unwind pool heap bind failed");pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Unwind ASM pool creation failed");input=Marshal.AllocHGlobal(n*128);output=Marshal.AllocHGlobal(n*32);for(int i=0;i<n;i++)Marshal.WriteInt64(input,i*128,i);
            Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(m,"boom_entry"),input,output,n)==0,"Concurrent exception pool dispatch failed");int first=0;for(int i=0;i<n;i++){long actual=Marshal.ReadInt64(output,i*32),expected=(i&3)==0?i+101:((i&1)==0?i+103:97);if(failure){Check(actual==71||actual==73,"Concurrent class failure type mismatch");if(actual==71)first++;expected=actual;}Check(actual==expected&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent catch/monitor result mismatch: "+i);}if(failure)Check(first==1,"Failed class initializer did not throw exactly one first-use exception");Idle(m,heap);GC(m,heap,IntPtr.Zero);
        }finally{if(pool!=IntPtr.Zero)Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(pool)==0,"Unwind pool shutdown failed");if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);Close(m,heap);FreeLibrary(r);}
    }
    public static void ClassFailureRoots(string dll,uint owner,uint firstField,uint lastField,uint failedClass,int wrappedCause,int laterCause){
        IntPtr m=Open(dll),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Class failure heap bind failed");var entry=Fn<Entry32>(m,"boom_entry32");var c=new Context32();Check(entry(ref c,new ulong[]{0})==71&&c.Kind==0,"First class failure was not wrapped");IntPtr first=Fn<Field>(m,"boom_get_static_field")(owner,firstField),last=Fn<Field>(m,"boom_get_static_field")(owner,lastField),original=Marshal.ReadIntPtr(first),desc=Fn<Layout>(m,"boom_get_class_descriptor")(failedClass),cell=Marshal.ReadIntPtr(desc,56);Check(Marshal.ReadInt32(desc,4)==2&&Marshal.ReadInt32(desc,8)==3&&original!=IntPtr.Zero&&Marshal.ReadIntPtr(cell)==original&&Marshal.ReadIntPtr(original,wrappedCause)!=IntPtr.Zero,"Class failure did not publish its actual rooted cause");IntPtr cause=Marshal.ReadIntPtr(original,wrappedCause);Marshal.WriteIntPtr(first,IntPtr.Zero);Marshal.WriteIntPtr(last,IntPtr.Zero);Idle(m,heap);GC(m,heap,IntPtr.Zero);Check(Marshal.ReadIntPtr(cell)==original&&Marshal.ReadIntPtr(original,wrappedCause)==cause,"Class-only failure graph was reclaimed");c=new Context32();Check(entry(ref c,new ulong[]{0})==73&&c.Kind==0,"Subsequent class failure did not become NoClassDefFoundError");IntPtr later=Marshal.ReadIntPtr(last);Check(later!=original&&Marshal.ReadIntPtr(later,laterCause)==original,"Subsequent class failure lost its cached cause");Idle(m,heap);GC(m,heap,IntPtr.Zero);
        }finally{Close(m,heap);}
    }
    public static void EmergencyOom(string dll,string runtime,uint owner,uint lastField){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{heap=Fn<Create>(m,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Emergency heap bind failed");var entry=Fn<Entry32>(m,"boom_entry32");var c=new Context32();Check(entry(ref c,new ulong[]{0})==89&&c.Kind==0,"Emergency warmup failed");GC(m,heap,IntPtr.Zero);IntPtr vm=Fn<Pointer>(m,"boom_get_exception_vm")(),oom=Marshal.ReadIntPtr(Marshal.ReadIntPtr(vm,96)),cell=Fn<Field>(m,"boom_get_static_field")(owner,lastField);Check(oom!=IntPtr.Zero&&Marshal.ReadIntPtr(cell)==oom,"OOM did not use the preallocated object");var alloc=Fn<Alloc>(r,"boom_heap_alloc");int blocks=0;while(alloc(heap,4096,0,267)!=IntPtr.Zero){Check(++blocks<1000,"Heap exceeded its budget");}while(alloc(heap,0,0,267)!=IntPtr.Zero){Check(++blocks<4096,"Heap exceeded its budget");}long before=Marshal.ReadInt64(heap,56);c=new Context32();Check(entry(ref c,new ulong[]{0})==89&&c.Kind==0&&c.Pending==IntPtr.Zero&&c.Depth==0&&Marshal.ReadIntPtr(cell)==oom&&Marshal.ReadInt64(heap,56)==before,"A completely full heap could not catch the preallocated OOM");Idle(m,heap);GC(m,heap,IntPtr.Zero);Check(Marshal.ReadIntPtr(cell)==oom,"Emergency OOM root was reclaimed");
        }finally{Close(m,heap);FreeLibrary(r);}
    }
}
