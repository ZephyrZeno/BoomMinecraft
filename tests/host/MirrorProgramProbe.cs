using System;
using System.Runtime.InteropServices;
public static class BoomMirrorProgramProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr heap,IntPtr pool,uint index,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Intrinsic(ref Context context,[In] ulong[] args,IntPtr pool,uint operation);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {var address=GetProcAddress(module,name);if(address==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(address);}
    static IntPtr Open(string path){var module=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(module==IntPtr.Zero)throw new Exception("Cannot open "+path);return module;}
    public static void Cold(string dll,string runtime,uint expectedHash) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Mirror heap binding failed");
            const int count=4099;var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=3;
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("Mirror worker creation failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Cold mirror run failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=expectedHash||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Cold mirror publication mismatch "+i);
            uint countRoots;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out countRoots);
            int liveRoots=0;for(int i=0;i<countRoots;i++)if(Marshal.ReadIntPtr(roots,i*8)!=IntPtr.Zero)liveRoots++;
            if(liveRoots!=2||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Mirror/name allocated more than once");
            if(Symbol<Collect>(module,"boom_heap_collect")(heap,roots,countRoots)!=0||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Mirror/name graph was collected");
            var context=new Context();if(Symbol<Entry>(module,"boom_entry")(ref context,new ulong[]{3})!=expectedHash||context.Kind!=0||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Cached mirror changed after collection");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
    public static void AbiAndFailure(string runtime) {
        IntPtr library=Open(runtime),heap=IntPtr.Zero,other=IntPtr.Zero,pool=IntPtr.Zero,roots=IntPtr.Zero,row=IntPtr.Zero,layout=IntPtr.Zero,type=IntPtr.Zero;
        try {
            var create=Symbol<HeapCreate>(library,"boom_heap_create");var collect=Symbol<Collect>(library,"boom_heap_collect");var alloc=Symbol<Alloc>(library,"boom_heap_alloc");
            var load=Symbol<Load>(library,"boom_mirror_load");var intrinsic=Symbol<Intrinsic>(library,"boom_mirror_intrinsic");
            heap=create(4096);other=create(4096);if(heap==IntPtr.Zero||other==IntPtr.Zero)throw new Exception("Mirror small heaps failed");
            pool=Marshal.AllocHGlobal(64);roots=Marshal.AllocHGlobal(8);row=Marshal.AllocHGlobal(24);layout=Marshal.AllocHGlobal(24);type=Marshal.AllocHGlobal(40);
            Marshal.Copy(new long[8],0,pool,8);Marshal.WriteIntPtr(roots,IntPtr.Zero);Marshal.Copy(new long[3],0,row,3);Marshal.Copy(new long[3],0,layout,3);Marshal.Copy(new long[5],0,type,5);
            Marshal.WriteInt32(pool,0,0x4d495252);Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,12,1);Marshal.WriteIntPtr(pool,16,roots);Marshal.WriteIntPtr(pool,24,row);Marshal.WriteIntPtr(pool,32,layout);
            Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,1);Marshal.WriteInt64(layout,8,8);Marshal.WriteInt32(layout,20,1);
            Marshal.WriteInt32(type,0,0x54595045);Marshal.WriteInt32(type,4,1);Marshal.WriteInt32(type,8,1);Marshal.WriteInt32(type,12,1);
            Marshal.WriteIntPtr(row,type);Marshal.WriteInt32(row,12,-1);Marshal.WriteInt32(row,16,-1);
            if(alloc(heap,3136,0,new IntPtr(1))==IntPtr.Zero)throw new Exception("Mirror OOM setup allocation failed");
            var context=new Context();if(load(heap,pool,0,ref context)!=IntPtr.Zero||context.Kind!=3||Marshal.ReadInt32(pool,8)!=0||Marshal.ReadIntPtr(roots)!=IntPtr.Zero)throw new Exception("Mirror OOM published a partial root or retained lock");
            context=new Context();if(load(other,pool,0,ref context)!=IntPtr.Zero||context.Kind!=7||Marshal.ReadInt32(pool,8)!=0)throw new Exception("Mirror accepted another heap");
            if(collect(heap,IntPtr.Zero,0)!=1)throw new Exception("Mirror OOM setup was not collected");
            context=new Context();IntPtr value=load(heap,pool,0,ref context);
            if(value==IntPtr.Zero||context.Kind!=0||Marshal.ReadIntPtr(roots)!=value||Marshal.ReadInt64(heap,56)!=1)throw new Exception("Mirror retry after GC failed");
            context=new Context();if(load(heap,pool,0,ref context)!=value||context.Kind!=0||Marshal.ReadInt64(heap,56)!=1)throw new Exception("Cached mirror was allocated again");
            context=new Context();load(heap,pool,1,ref context);if(context.Kind!=7)throw new Exception("Mirror accepted invalid type ID");
            Marshal.WriteInt32(pool,4,2);context=new Context();load(heap,pool,0,ref context);if(context.Kind!=7)throw new Exception("Mirror accepted incompatible ABI");Marshal.WriteInt32(pool,4,1);
            context=new Context();intrinsic(ref context,new ulong[]{unchecked((ulong)value.ToInt64())},pool,255);if(context.Kind!=7)throw new Exception("Mirror accepted invalid intrinsic ID");
            context=new Context();intrinsic(ref context,new ulong[]{0},pool,1);if(context.Kind!=4)throw new Exception("Mirror null receiver was accepted");
            context=new Context();if(intrinsic(ref context,new ulong[]{unchecked((ulong)value.ToInt64())},pool,4)!=0||context.Kind!=0)throw new Exception("Object superclass must be null");
            IntPtr forged=alloc(heap,8,0,layout);context=new Context();intrinsic(ref context,new ulong[]{unchecked((ulong)forged.ToInt64())},pool,1);if(context.Kind!=7)throw new Exception("Uncached mirror with matching layout was accepted");
            if(collect(heap,roots,1)!=1||Marshal.ReadInt64(heap,56)!=1)throw new Exception("Mirror cached root was not preserved");
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(heap);if(other!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(other);foreach(var value in new[]{pool,roots,row,layout,type})if(value!=IntPtr.Zero)Marshal.FreeHGlobal(value);FreeLibrary(library);}
    }
}
