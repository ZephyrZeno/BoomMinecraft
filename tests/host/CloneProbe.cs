// Development verification host. Allocation, copying, workers and GC execute MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class BoomCloneProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind, PC, Method, Depth; }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p, IntPtr z, uint f);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m, string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Get();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h, IntPtr roots, uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h, ulong bytes, uint refs, ulong type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c, [In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Clone(ref Context c, [In] ulong[] args, IntPtr pool, IntPtr type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p, IntPtr fn, IntPtr input, IntPtr output, uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();

    static void Check(bool ok, string message) { if (!ok) throw new Exception(message); }
    static IntPtr Open(string path) { IntPtr m=LoadLibraryExW(path, IntPtr.Zero, 0x1100); Check(m!=IntPtr.Zero,"Cannot load clone test module"); return m; }
    static T Fn<T>(IntPtr m, string name) { IntPtr p=GetProcAddress(m,name); Check(p!=IntPtr.Zero,"Missing "+name); return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static void Close(IntPtr m, IntPtr h) {
        IntPtr p=GetProcAddress(m,"boom_release_trace_pool");
        if(p!=IntPtr.Zero) Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"Clone Java frames still active");
        if(h!=IntPtr.Zero) Check(Fn<Destroy>(m,"boom_heap_destroy")(h)!=0,"Clone heap cleanup failed");
        Check(FreeLibrary(m),"Clone module cleanup failed");
    }
    static ulong Address(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    static IntPtr Array(Entry entry, int selector) {
        var ctx=new Context(); IntPtr p=new IntPtr(unchecked((long)entry(ref ctx,new ulong[]{unchecked((uint)selector)})));
        Check(p!=IntPtr.Zero && ctx.Kind==0 && ctx.Depth==0,"Array fixture failed: "+selector+"/"+ctx.Kind); return p;
    }
    static IntPtr Copy(Clone clone, IntPtr source, IntPtr pool, IntPtr type) {
        var ctx=new Context(); IntPtr p=clone(ref ctx,new ulong[]{Address(source)},pool,type);
        Check(p!=IntPtr.Zero && ctx.Kind==0 && ctx.Depth==0,"Native clone failed: "+ctx.Kind); return p;
    }
    static IntPtr TypeOf(IntPtr pool, IntPtr source) {
        IntPtr map=Marshal.ReadIntPtr(pool,16), rows=Marshal.ReadIntPtr(map,16);
        long tag=Marshal.ReadInt64(source,-8); int count=Marshal.ReadInt32(map,8);
        for(int i=0;i<count;i++) if(Marshal.ReadInt64(rows,i*40)==tag) return Marshal.ReadIntPtr(rows,i*40+8);
        throw new Exception("Source tag absent from clone runtime map");
    }
    static int Reachable(IntPtr roots, uint n) {
        var live=new HashSet<IntPtr>(); var todo=new Stack<IntPtr>();
        for(int i=0;i<n;i++) todo.Push(Marshal.ReadIntPtr(roots,i*8));
        while(todo.Count!=0) {
            IntPtr p=todo.Pop(); if(p==IntPtr.Zero || !live.Add(p)) continue;
            uint flags=unchecked((uint)Marshal.ReadInt32(p,-24)), refs=unchecked((uint)Marshal.ReadInt32(p,-20));
            long bytes=Marshal.ReadInt64(p,-16);
            Check((flags&0xfffffffd)==0xb00b0001 && bytes>=0 && refs<=(ulong)bytes/8 && live.Count<1048576,"Malformed clone root graph");
            for(int i=0;i<refs;i++) todo.Push(Marshal.ReadIntPtr(p,i*8));
        }
        return live.Count;
    }
    static void GC(IntPtr m, IntPtr h, params IntPtr[] extra) {
        IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n), all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));
        try {
            for(int i=0;i<n;i++) Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));
            for(int i=0;i<extra.Length;i++) Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);
            int expected=Reachable(all,n+(uint)extra.Length);
            Check(Fn<Collect>(m,"boom_heap_collect")(h,all,n+(uint)extra.Length)!=ulong.MaxValue,"Clone collection failed");
            Check(Marshal.ReadInt64(h,56)==expected,"Clone reference prefix/root graph lost or retained objects");
        } finally { Marshal.FreeHGlobal(all); }
    }
    static byte[] Bytes(IntPtr p) { byte[] b=new byte[checked((int)Marshal.ReadInt64(p,-16))]; if(b.Length!=0) Marshal.Copy(p,b,0,b.Length); return b; }
    static bool Same(byte[] a, byte[] b) { if(a.Length!=b.Length)return false; for(int i=0;i<a.Length;i++)if(a[i]!=b[i])return false; return true; }
    static void EqualClone(IntPtr source, IntPtr copy) {
        Check(source!=copy && Marshal.ReadInt64(source,-16)==Marshal.ReadInt64(copy,-16) && Marshal.ReadInt32(source,-20)==Marshal.ReadInt32(copy,-20) && Marshal.ReadInt64(source,-8)==Marshal.ReadInt64(copy,-8),"Clone identity, runtime type or reference prefix changed");
        Check(Same(Bytes(source),Bytes(copy)),"Clone payload bits differ");
    }

    public static void Native(string dll, string runtime) {
        IntPtr m=Open(dll),r=Open(runtime),h=IntPtr.Zero;
        try {
            h=Fn<Create>(m,"boom_heap_create")(2*1024*1024);
            Check(h!=IntPtr.Zero && Fn<Bind>(m,"boom_bind_heap")(h)==1,"Clone heap setup failed");
            var entry=Fn<Entry>(m,"boom_entry"); var clone=Fn<Clone>(m,"boom_array_clone");
            IntPtr pool=Fn<Get>(m,"boom_get_array_clone_pool")();
            IntPtr objectArray=Array(entry,16|10), objectType=TypeOf(pool,objectArray); GC(m,h);
            for(int empty=0;empty<2;empty++) for(int kind=0;kind<11;kind++) {
                IntPtr source=Array(entry,(0x1234<<8)|16|(empty*32)|kind), type=TypeOf(pool,source);
                byte[] before=Bytes(source); long count=Marshal.ReadInt64(h,56);
                IntPtr copy=Copy(clone,source,pool,kind==8?objectType:type);
                EqualClone(source,copy); Check(Marshal.ReadInt64(h,56)==count+1,"Clone made more than one guest allocation");
                if(before.Length!=0) {
                    if(kind<8) { byte first=Marshal.ReadByte(source); Marshal.WriteByte(copy,0,(byte)(first^0x5a)); Check(Marshal.ReadByte(source)==first,"Primitive clone aliases source storage"); }
                    else { IntPtr first=Marshal.ReadIntPtr(source); Marshal.WriteIntPtr(copy,IntPtr.Zero); Check(Marshal.ReadIntPtr(source)==first,"Reference clone aliases source slots"); Marshal.WriteIntPtr(copy,first); }
                }
                // Drop the source root. Reference elements must survive through the clone alone.
                GC(m,h,copy);
                if(kind>=8 && before.Length!=0) Check(Marshal.ReadIntPtr(copy)!=IntPtr.Zero,"Clone reference element was lost");
                GC(m,h);
            }
            // Raw floating payloads, including signaling NaNs, bypass host FP conversions.
            var alloc=Fn<Alloc>(r,"boom_heap_alloc"); var random=new Random(41041);
            for(int kind=6;kind<8;kind++) {
                IntPtr sample=Array(entry,16|kind), type=TypeOf(pool,sample); ulong tag=unchecked((ulong)Marshal.ReadInt64(sample,-8)); GC(m,h);
                for(int batch=0;batch<64;batch++) {
                    byte[] bits=new byte[kind==6?1024:2048]; random.NextBytes(bits);
                    byte[] edge=kind==6?new byte[]{1,0,128,127,0,0,0,128}:new byte[]{1,0,0,0,0,0,240,127,0,0,0,0,0,0,0,128};
                    System.Array.Copy(edge,bits,edge.Length);
                    IntPtr source=alloc(h,(ulong)bits.Length,0,tag); Check(source!=IntPtr.Zero,"Raw clone allocation failed"); Marshal.Copy(bits,0,source,bits.Length);
                    long count=Marshal.ReadInt64(h,56); IntPtr copy=Copy(clone,source,pool,type); EqualClone(source,copy);
                    Check(Marshal.ReadInt64(h,56)==count+1,"Raw clone allocation count changed"); GC(m,h,copy); Check(Same(bits,Bytes(copy)),"Raw clone GC changed payload"); GC(m,h);
                }
            }
            IntPtr input=Array(entry,16|4), expectedType=TypeOf(pool,input); GC(m,h,input);
            var c=new Context{Kind=9,PC=17,Method=23,Depth=3};
            Check(clone(ref c,new ulong[]{0},IntPtr.Zero,IntPtr.Zero)==IntPtr.Zero && c.Kind==9 && c.PC==17 && c.Method==23 && c.Depth==3,"Clone changed a pending exception");
            c=new Context{PC=17,Method=23}; Check(clone(ref c,new ulong[]{0},pool,expectedType)==IntPtr.Zero && c.Kind==4 && c.PC==17 && c.Method==23,"Clone null receiver order failed");
            long baseline=Marshal.ReadInt64(h,56);
            IntPtr badPool=Marshal.AllocHGlobal(32), badType=Marshal.AllocHGlobal(40), cell=Marshal.AllocHGlobal(8);
            try {
                byte[] data=new byte[32]; Marshal.Copy(pool,data,0,32);
                foreach(int offset in new int[]{0,4,8,16,24}) {
                    Marshal.Copy(data,0,badPool,32);
                    if(offset<8)Marshal.WriteInt32(badPool,offset,7); else Marshal.WriteIntPtr(badPool,offset,offset==24?new IntPtr(1):IntPtr.Zero);
                    c=new Context(); Check(clone(ref c,new ulong[]{Address(input)},badPool,expectedType)==IntPtr.Zero && c.Kind==7,"Clone accepted malformed pool: "+offset);
                }
                byte[] td=new byte[40]; Marshal.Copy(expectedType,td,0,40);
                foreach(int offset in new int[]{0,4,8}) {
                    Marshal.Copy(td,0,badType,40); Marshal.WriteInt32(badType,offset,offset==8?1:7);
                    c=new Context(); Check(clone(ref c,new ulong[]{Address(input)},pool,badType)==IntPtr.Zero && c.Kind==7,"Clone accepted malformed owner type");
                }
                IntPtr other=Array(entry,16|1); c=new Context(); Check(clone(ref c,new ulong[]{Address(input)},pool,TypeOf(pool,other))==IntPtr.Zero && c.Kind==7,"Clone accepted incompatible symbolic array owner"); GC(m,h,input); baseline=Marshal.ReadInt64(h,56);
                IntPtr foreign=Fn<Create>(m,"boom_heap_create")(65536); Check(foreign!=IntPtr.Zero,"Foreign clone heap failed");
                try {
                    Marshal.Copy(data,0,badPool,32); Marshal.WriteIntPtr(cell,foreign); Marshal.WriteIntPtr(badPool,8,cell);
                    c=new Context(); Check(clone(ref c,new ulong[]{Address(input)},badPool,expectedType)==IntPtr.Zero && c.Kind==7,"Clone accepted a foreign heap source");
                } finally { Check(Fn<Destroy>(m,"boom_heap_destroy")(foreign)!=0,"Foreign heap cleanup failed"); }
                foreach(int offset in new int[]{-32,-24,-20,-16,-8}) {
                    long old=Marshal.ReadInt64(input,offset); Marshal.WriteInt64(input,offset,offset==-8?123:offset==-16?4096:offset==-20?(old|1):0);
                    c=new Context(); Check(clone(ref c,new ulong[]{Address(input)},pool,expectedType)==IntPtr.Zero && c.Kind==7,"Clone accepted malformed array header: "+offset);
                    Marshal.WriteInt64(input,offset,old);
                }
                Check(Marshal.ReadInt64(h,56)==baseline,"Clone validation allocated guest objects");
            } finally { Marshal.FreeHGlobal(badPool); Marshal.FreeHGlobal(badType); Marshal.FreeHGlobal(cell); }
            while(alloc(h,4096,0,267)!=IntPtr.Zero){} while(alloc(h,0,0,267)!=IntPtr.Zero){}
            long full=Marshal.ReadInt64(h,56); byte[] original=Bytes(input);
            for(int i=0;i<128;i++) { c=new Context{PC=17,Method=23}; Check(clone(ref c,new ulong[]{Address(input)},pool,expectedType)==IntPtr.Zero && c.Kind==3 && c.PC==17 && c.Method==23 && Marshal.ReadInt64(h,56)==full,"Clone full-heap failure changed source/count/context"); }
            Check(Same(original,Bytes(input)),"Failed clone modified source"); GC(m,h,input);
            IntPtr recovered=Copy(clone,input,pool,expectedType); EqualClone(input,recovered); GC(m,h);
        } finally { Close(m,h); Check(FreeLibrary(r),"Runtime cleanup failed"); }
    }

    public static void Tail(string dll, string runtime) {
        IntPtr m=Open(dll),r=Open(runtime),h=IntPtr.Zero;
        try {
            h=Fn<Create>(m,"boom_heap_create")(65536); Check(h!=IntPtr.Zero && Fn<Bind>(m,"boom_bind_heap")(h)==1,"Tail clone setup failed");
            IntPtr sample=Array(Fn<Entry>(m,"boom_entry"),16|32|4), pool=Fn<Get>(m,"boom_get_array_clone_pool")(), type=TypeOf(pool,sample);
            GC(m,h); var alloc=Fn<Alloc>(r,"boom_heap_alloc");
            long left=Marshal.ReadInt64(h,16)-Marshal.ReadInt64(h,48); if((left&31)!=0)Check(alloc(h,16,0,267)!=IntPtr.Zero,"Tail clone alignment failed");
            IntPtr last=IntPtr.Zero,v; while((v=alloc(h,0,0,266))!=IntPtr.Zero)last=v;
            Check(last!=IntPtr.Zero && last==Marshal.ReadIntPtr(h,24),"Empty clone source did not reach exact heap end");
            var c=new Context(); Check(Fn<Clone>(m,"boom_array_clone")(ref c,new ulong[]{Address(last)},pool,type)==IntPtr.Zero && c.Kind==3,"Valid empty tail source was rejected before allocation");
            GC(m,h,last); long before=Marshal.ReadInt64(h,56); IntPtr copy=Copy(Fn<Clone>(m,"boom_array_clone"),last,pool,type); EqualClone(last,copy);
            Check(Marshal.ReadInt64(h,56)==before+1,"Empty clone allocation count changed"); GC(m,h,copy);
        } finally { Close(m,h); Check(FreeLibrary(r),"Tail runtime cleanup failed"); }
    }

    public static void FullHeap(string dll, string runtime) {
        IntPtr m=Open(dll),r=Open(runtime),h=IntPtr.Zero;
        try {
            h=Fn<Create>(m,"boom_heap_create")(65536); Check(h!=IntPtr.Zero && Fn<Bind>(m,"boom_bind_heap")(h)==1,"Compiled clone OOM setup failed");
            var entry=Fn<Entry>(m,"boom_entry");
            for(uint i=0;i<4;i++){var c=new Context(); Check(entry(ref c,new ulong[]{i})==(i%2==0?3UL:23UL) && c.Kind==0,"Compiled clone warmup failed");}
            GC(m,h); var alloc=Fn<Alloc>(r,"boom_heap_alloc"); while(alloc(h,4096,0,267)!=IntPtr.Zero){} while(alloc(h,0,0,267)!=IntPtr.Zero){}
            long full=Marshal.ReadInt64(h,56);
            for(uint i=0;i<256;i++){var c=new Context(); Check(entry(ref c,new ulong[]{i})==(i%2==0?3UL:97UL) && c.Kind==0 && c.Depth==0 && Marshal.ReadInt64(h,56)==full,"Original Java clone OOM catch failed");}
            GC(m,h);
        } finally { Close(m,h); Check(FreeLibrary(r),"OOM runtime cleanup failed"); }
    }

    public static void Parallel(string dll, string runtime, int[] expected) {
        const uint n=2049; IntPtr m=Open(dll),r=Open(runtime),h=IntPtr.Zero,p=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            h=Fn<Create>(m,"boom_heap_create")(16*1024*1024); Check(h!=IntPtr.Zero && Fn<Bind>(m,"boom_bind_heap")(h)==1 && expected.Length==n,"Clone worker setup failed");
            p=Fn<PoolCreate>(r,"boom_pool_create")(8); Check(p!=IntPtr.Zero,"Clone worker pool failed");
            input=Marshal.AllocHGlobal((int)n*128); output=Marshal.AllocHGlobal((int)n*32);
            for(int i=0;i<n;i++)Marshal.WriteInt64(input,i*128,i);
            for(int batch=0;batch<3;batch++) {
                Check(Fn<PoolRun>(r,"boom_pool_run")(p,GetProcAddress(m,"boom_entry"),input,output,n)==0,"Clone worker batch failed");
                for(int i=0;i<n;i++)Check(unchecked((int)Marshal.ReadInt64(output,i*32))==expected[i] && Marshal.ReadInt64(output,i*32+8)==0 && Marshal.ReadInt64(output,i*32+16)==0 && Marshal.ReadInt64(output,i*32+24)==0,"Clone worker result/context mismatch");
                GC(m,h);
            }
        } finally {
            if(p!=IntPtr.Zero)Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(p)==0,"Clone workers active at cleanup");
            if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input); if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output); Close(m,h); Check(FreeLibrary(r),"Worker runtime cleanup failed");
        }
    }
}
