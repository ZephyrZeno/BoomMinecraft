// Development-only driver. Joining, callbacks, workers, heap and collection are MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomJoinProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr r,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Join module load failed");return m;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static uint Hash(int n){uint h=0;unchecked{for(int i=0;i<n;i++){if(i!=0){h=h*31+58;h=h*31+58;}h=h*31+120;}}return h;}
    public static void Parallel(string dll,string runtime){
        IntPtr module=Open(dll),library=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Join heap failed");
            const int count=2049;long[] args=new long[count*16];long temporaries=0;
            for(int i=0;i<count;i++){args[i*16]=unchecked((uint)(0x80000000U+(uint)i*17));int n=(int)(args[i*16]&31);temporaries+=5+(n>8?1:0)+(n>16?1:0);}
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Join workers failed");long retained=-1;
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Join parallel dispatch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==Hash((int)(args[i*16]&31))&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent join result/context mismatch");
                long live=Marshal.ReadInt64(heap,56);IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint nRoots);
                Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,nRoots)==(ulong)temporaries,"Join temporary allocation count differs from vectors, iterators and result buffers");
                long current=Marshal.ReadInt64(heap,56);Check(current>0&&live==temporaries+current&&(retained<0||current==retained),"Join buffers leaked or literal roots changed");retained=current;
            }
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(library);FreeLibrary(module);}
    }
    public static void Budget(string dll,uint method){
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(4096);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Join small heap failed");var entry=Fn<Entry>(module,"boom_entry");
            var c=new Context();entry(ref c,new ulong[]{256});Check(c.Kind==3&&c.Method==method&&c.PC!=0&&c.Depth==0&&Marshal.ReadInt64(heap,56)>6,"Join vector OOM escaped budget or lost source origin");
            IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint count);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,count)>0,"Join OOM temporary graph was not reclaimed");long retained=Marshal.ReadInt64(heap,56);
            c=new Context();Check(unchecked((uint)entry(ref c,new ulong[]{2}))==Hash(2)&&c.Kind==0&&c.Depth==0,"Join did not recover after quiescent OOM collection");
            roots=Fn<Roots>(module,"boom_get_static_roots")(out count);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,count)>0&&Marshal.ReadInt64(heap,56)==retained,"Join recovery leaked temporaries or roots");
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
    public static void Provenance(string dll,uint entryMethod,uint sequence,uint next,uint hasNext){
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Join provenance heap failed");var entry=Fn<Entry>(module,"boom_entry");
            ulong[][] cases={new ulong[]{1,2,0,1},new ulong[]{2,3,0,3},new ulong[]{2,3,0,5},new ulong[]{4,0,7,0},new ulong[]{5,0,7,0},new ulong[]{3,2,0,0},new ulong[]{1,2,6,0}};
            uint[] kinds={2,2,2,2,4,12,4},methods={sequence,next,hasNext,sequence,entryMethod,entryMethod,entryMethod};
            for(int i=0;i<cases.Length;i++){
                var c=new Context();entry(ref c,cases[i]);Check(c.Kind==kinds[i]&&c.Method==methods[i]&&c.PC!=0&&c.Depth==0,"Join exception source mismatch case "+i+": kind="+c.Kind+" method="+c.Method+" pc="+c.PC+" depth="+c.Depth+"; expected kind="+kinds[i]+" method="+methods[i]);
                IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,n)!=ulong.MaxValue,"Join callback failure graph collection failed");
            }
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
}
