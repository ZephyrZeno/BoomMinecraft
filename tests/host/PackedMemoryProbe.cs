using System;
using System.Runtime.InteropServices;
// Diagnostic host: allocation, compiled Java, byte stores, workers and GC are ASM.
public static class BoomPackedMemoryProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Check(IntPtr value,IntPtr layout,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RefNew(IntPtr heap,int count,IntPtr layout,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    static T Symbol<T>(IntPtr module,string name)where T:Delegate {var p=GetProcAddress(module,name);if(p==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string path){var m=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(m==IntPtr.Zero)throw new Exception("Cannot open "+path);return m;}
    public sealed class Measurement {public int graphs,objects;public long payload_per_root,reserved_bytes;public int layout_abi;public bool retained,reclaimed,reused;}
    public static Measurement Measure(string dll,int count,int objectsPerGraph,int expectedPayload,int expectedAbi,bool grand) {
        IntPtr module=Open(dll),heap=IntPtr.Zero,roots=IntPtr.Zero;
        try{
            heap=Symbol<HeapCreate>(module,"boom_heap_create")(64*1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Memory comparison heap failed");
            roots=Marshal.AllocHGlobal(count*8);var entry=Symbol<Entry>(module,"boom_entry");
            for(int i=0;i<count;i++) {
                var context=new Context();var arguments=grand?new[]{2UL,unchecked((ulong)(uint)i)}:new[]{unchecked((ulong)(uint)i)};
                var value=new IntPtr(unchecked((long)entry(ref context,arguments)));
                if(context.Kind!=0||context.Depth!=0||value==IntPtr.Zero||Marshal.ReadInt64(value,-16)!=expectedPayload||Marshal.ReadInt32(Marshal.ReadIntPtr(value,-8),4)!=expectedAbi)throw new Exception("Factory/layout comparison failed");
                Marshal.WriteIntPtr(roots,i*8,value);
            }
            long bytes=Marshal.ReadInt64(heap,48);int objects=checked(count*objectsPerGraph);
            if(Marshal.ReadInt64(heap,56)!=objects)throw new Exception("Factory allocated a different graph");
            var collect=Symbol<Collect>(module,"boom_heap_collect");
            if(collect(heap,roots,(uint)count)!=0||Marshal.ReadInt64(heap,48)!=bytes||Marshal.ReadInt64(heap,56)!=objects)throw new Exception("Live packed graph was not retained");
            if(collect(heap,IntPtr.Zero,0)!=(ulong)objects||Marshal.ReadInt64(heap,48)!=0)throw new Exception("Unrooted packed graph leaked");
            var finalContext=new Context();entry(ref finalContext,grand?new[]{2UL,7UL}:new[]{7UL});
            if(finalContext.Kind!=0||collect(heap,IntPtr.Zero,0)!=(ulong)objectsPerGraph||Marshal.ReadInt64(heap,48)!=0)throw new Exception("Packed heap reuse failed");
            return new Measurement{graphs=count,objects=objects,payload_per_root=expectedPayload,reserved_bytes=bytes,layout_abi=expectedAbi,retained=true,reclaimed=true,reused=true};
        }finally{if(roots!=IntPtr.Zero)Marshal.FreeHGlobal(roots);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
    public static void SharedBytes(string dll,string runtime,int left,int right,int[] flags,int expectedPayload) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(4*1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Shared byte heap failed");
            const int count=65539;var values=new long[count*16];for(int i=0;i<count;i++){values[i*16]=i&1;values[i*16+1]=(i&1)==0?0x5a:0xa5;}
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("Shared byte pool failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Shared byte execution failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=1||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Shared byte context mismatch");
            uint rootCount;var roots=Symbol<Roots>(module,"boom_get_static_roots")(out rootCount);IntPtr root=IntPtr.Zero;
            for(int i=0;i<rootCount;i++){var p=Marshal.ReadIntPtr(roots,i*8);if(p!=IntPtr.Zero){if(root!=IntPtr.Zero)throw new Exception("Unexpected packed static root");root=p;}}
            if(root==IntPtr.Zero||Marshal.ReadInt64(root,-16)!=expectedPayload||Marshal.ReadByte(root,left)!=0x5a||Marshal.ReadByte(root,right)!=0xa5)throw new Exception("Adjacent independent byte fields interfered");
            foreach(int offset in flags)if(Marshal.ReadByte(root,offset)!=1)throw new Exception("Byte store overwrote a neighboring boolean");
            if(Symbol<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)!=0||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Packed shared references were lost");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
    public static int Capacity(string dll,int budget,int objectsPerGraph,bool grand) {
        IntPtr module=Open(dll),heap=IntPtr.Zero,roots=IntPtr.Zero;
        try {
            heap=Symbol<HeapCreate>(module,"boom_heap_create")((ulong)budget);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Capacity heap failed");
            roots=Marshal.AllocHGlobal(1024*8);var entry=Symbol<Entry>(module,"boom_entry");int count=0;
            for(;count<1024;count++) {
                var context=new Context();var value=new IntPtr(unchecked((long)entry(ref context,grand?new[]{2UL,7UL}:new[]{7UL})));
                if(context.Kind==3){if(value!=IntPtr.Zero||context.Depth!=0)throw new Exception("OOM did not unwind factory");break;}
                if(context.Kind!=0||value==IntPtr.Zero)throw new Exception("Unexpected capacity failure");
                Marshal.WriteIntPtr(roots,count*8,value);
            }
            if(count==0||count==1024)throw new Exception("Capacity check did not reach a bounded OOM");
            var collect=Symbol<Collect>(module,"boom_heap_collect");collect(heap,roots,(uint)count);
            if(Marshal.ReadInt64(heap,56)!=count*objectsPerGraph)throw new Exception("OOM damaged surviving objects or leaked partial construction");
            if(collect(heap,IntPtr.Zero,0)!=(ulong)(count*objectsPerGraph)||Marshal.ReadInt64(heap,48)!=0)throw new Exception("Capacity roots leaked");
            var retryContext=new Context();var retry=entry(ref retryContext,grand?new[]{2UL,7UL}:new[]{7UL});
            if(retryContext.Kind!=0||retryContext.Depth!=0||retry==0||collect(heap,IntPtr.Zero,0)!=(ulong)objectsPerGraph||Marshal.ReadInt64(heap,48)!=0)throw new Exception("Explicit collection did not permit recovery after constructor OOM");
            return count;
        }finally{if(roots!=IntPtr.Zero)Marshal.FreeHGlobal(roots);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
    public static void Abi(string runtime) {
        IntPtr library=Open(runtime),heap=IntPtr.Zero,layout=IntPtr.Zero,array=IntPtr.Zero;
        try{
            heap=Symbol<HeapCreate>(library,"boom_heap_create")(1024*1024);layout=Marshal.AllocHGlobal(24);Marshal.Copy(new byte[24],0,layout,24);
            Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,2);Marshal.WriteInt64(layout,8,4);Marshal.WriteInt32(layout,20,1);
            var make=Symbol<Make>(library,"boom_object_new");var check=Symbol<Check>(library,"boom_object_check");var context=new Context();var value=make(heap,layout,ref context);
            if(value==IntPtr.Zero||context.Kind!=0||Marshal.ReadInt64(value,-16)!=4||Marshal.ReadInt32(value)!=0)throw new Exception("Compact object ABI allocation failed");
            context=new Context();if(check(value,layout,ref context)!=value||context.Kind!=0)throw new Exception("Compact object ABI check failed");
            foreach(int abi in new[]{0,3,99}){Marshal.WriteInt32(layout,4,abi);context=new Context();if(make(heap,layout,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Unknown object layout ABI accepted");context=new Context();check(value,layout,ref context);if(context.Kind!=7)throw new Exception("Unknown ABI accepted for field access");}
            Marshal.WriteInt32(layout,4,2);Marshal.WriteInt32(layout,16,1);context=new Context();if(make(heap,layout,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Truncated reference prefix accepted");
            Marshal.WriteInt32(layout,16,0);Marshal.WriteInt64(layout,8,9);context=new Context();if(make(heap,layout,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Oversized compact single field accepted");
            Marshal.WriteInt64(layout,8,0);context=new Context();if(make(heap,layout,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Zero-byte nonempty object accepted");
            Marshal.WriteInt64(layout,8,4);Marshal.WriteInt32(layout,4,1);context=new Context();if(make(heap,layout,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Compact payload misidentified as legacy layout");
            Marshal.WriteInt32(layout,4,2);array=Marshal.AllocHGlobal(16);Marshal.WriteInt32(array,0,0x52454641);Marshal.WriteInt32(array,4,1);Marshal.WriteIntPtr(array,8,layout);
            context=new Context();if(Symbol<RefNew>(library,"boom_reference_array_new")(heap,2,array,ref context)==IntPtr.Zero||context.Kind!=0)throw new Exception("Reference array rejected compact component");
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(heap);if(layout!=IntPtr.Zero)Marshal.FreeHGlobal(layout);if(array!=IntPtr.Zero)Marshal.FreeHGlobal(array);FreeLibrary(library);}
    }
}
