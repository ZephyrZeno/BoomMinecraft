// Development host only. Guest lambda allocation/invocation, workers and GC execute MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomLambdaProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolDestroy(IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint owner,uint index);
    static void Check(bool value,string message) { if(!value)throw new Exception(message); }
    static T Fn<T>(IntPtr module,string name) { IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    public static void Parallel(string dll,string runtime,int mode,uint owner,uint field) {
        bool cached=mode==1;
        IntPtr module=IntPtr.Zero,library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);library=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);Check(module!=IntPtr.Zero&&library!=IntPtr.Zero,"Lambda DLL load failed");
            heap=Fn<Create>(module,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Lambda heap binding failed");
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Lambda pool creation failed");
            const int count=8195;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);
            var values=new long[count*16];
            for(int i=0;i<count;i++) { values[i*16]=unchecked((uint)(i*7919-int.MaxValue));values[i*16+1]=unchecked((uint)(i*-17+11)); }
            Marshal.Copy(values,0,input,values.Length);
            long retained=-1;
            for(int round=0;round<3;round++) {
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Lambda worker dispatch failed");
                for(int i=0;i<count;i++) {
                    uint a=unchecked((uint)values[i*16]),b=unchecked((uint)values[i*16+1]);
                    uint expected=cached?unchecked((3506402u^a)+100u):mode>=2?unchecked(a*2u+3u):unchecked(a*7u+b);
                    Check(Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0&&unchecked((uint)Marshal.ReadInt64(output,i*32))==expected,"Lambda parallel result/context mismatch at "+i);
                }
                if(cached) { IntPtr counter=Fn<Field>(module,"boom_get_static_field")(owner,field);Check(counter!=IntPtr.Zero&&Marshal.ReadInt32(counter)==1,"Lambda initializer ran more than once"); }
                if(mode>=2)Check(Marshal.ReadInt64(heap,56)==(mode==2?count:1),"Stateless lambda allocation count mismatch");
                IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint rootsCount);
                ulong reclaimed=Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootsCount);
                Check(reclaimed!=ulong.MaxValue,"Lambda post-batch GC failed");
                if(mode>=2)Check(reclaimed==(mode==2?(ulong)count:0),"Stateless lambda reclaim count mismatch");
                long live=Marshal.ReadInt64(heap,56);Check((cached?live>=2:live==(mode==3?1:0))&& (retained<0||live==retained),"Lambda roots leaked or were reclaimed across batches");retained=live;
                if(cached) {
                    IntPtr closure=Marshal.ReadIntPtr(Fn<Field>(module,"boom_get_static_field")(owner,field+1));
                    // Caller supplies the count field index; declaration order places f immediately after it.
                    Check(closure!=IntPtr.Zero&&Marshal.ReadIntPtr(closure)!=IntPtr.Zero,"Lambda captured reference was reclaimed");
                }
            }
        } finally {
            if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);
            if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);
            if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);
            if(library!=IntPtr.Zero)FreeLibrary(library);if(module!=IntPtr.Zero)FreeLibrary(module);
        }
    }
}
