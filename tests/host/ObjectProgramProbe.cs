using System;
using System.Runtime.InteropServices;
public static class BoomObjectProgramProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewObject(IntPtr heap,IntPtr layout,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {IntPtr address=GetProcAddress(module,name);if(address==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(address);}
    static IntPtr Open(string path){IntPtr module=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(module==IntPtr.Zero)throw new Exception("Cannot open "+path);return module;}
    public static void ColdGraph(string dll,string runtime,uint nodeId,uint boxId,int next,int box,int children,int numbers,int owner,int boxValue) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(16*1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Object graph heap failed");
            const int count=4099;var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=i;
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("Object graph pool failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Cold graph run failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=85+i||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Partially initialized object graph observed "+i);
            uint rootCount;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out rootCount);
            if(rootCount!=2)throw new Exception("Unexpected object static root count");
            IntPtr first=Marshal.ReadIntPtr(roots),second=Marshal.ReadIntPtr(first,next),firstBox=Marshal.ReadIntPtr(first,box),secondBox=Marshal.ReadIntPtr(second,box),array=Marshal.ReadIntPtr(first,children),data=Marshal.ReadIntPtr(first,numbers);
            var layout=Symbol<Layout>(module,"boom_get_object_layout");
            if(Marshal.ReadIntPtr(roots,8)!=first||Marshal.ReadIntPtr(first,-8)!=layout(nodeId)||Marshal.ReadIntPtr(second,-8)!=layout(nodeId)||Marshal.ReadIntPtr(firstBox,-8)!=layout(boxId)||layout(uint.MaxValue)!=IntPtr.Zero)throw new Exception("Object identity/layout mismatch");
            if(Marshal.ReadIntPtr(second,next)!=first||Marshal.ReadIntPtr(firstBox,owner)!=first||Marshal.ReadIntPtr(secondBox,owner)!=second||Marshal.ReadInt32(firstBox,boxValue)!=17||Marshal.ReadInt32(secondBox,boxValue)!=23||Marshal.ReadIntPtr(array)!=second||Marshal.ReadIntPtr(array,8)!=first||Marshal.ReadInt64(data,-16)!=44)throw new Exception("Cross-class graph fields were not published");
            var collect=Symbol<Collect>(module,"boom_heap_collect");
            if(collect(heap,roots,rootCount)!=0||Marshal.ReadInt64(heap,56)!=6)throw new Exception("Static object graph was not retained");
            Marshal.WriteIntPtr(first,next,IntPtr.Zero);Marshal.WriteIntPtr(array,0,IntPtr.Zero);
            if(collect(heap,roots,rootCount)!=2||Marshal.ReadInt64(heap,56)!=4)throw new Exception("Detached cross-class cycle was not reclaimed");
            Marshal.WriteIntPtr(roots,IntPtr.Zero);Marshal.WriteIntPtr(roots,8,IntPtr.Zero);
            if(collect(heap,roots,rootCount)!=4||Marshal.ReadInt64(heap,56)!=0)throw new Exception("Cleared static object graph leaked");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
    public static void ReceiverChecks(string dll,string runtime,uint nodeId,uint boxId,uint entryId) {
        IntPtr module=Open(dll),heap=IntPtr.Zero,library=IntPtr.Zero;
        try {
            library=Open(runtime);
            heap=Symbol<HeapCreate>(module,"boom_heap_create")(1024*1024);if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Receiver heap failed");
            var layout=Symbol<Layout>(module,"boom_get_object_layout");var create=Symbol<NewObject>(library,"boom_object_new");var entry=Symbol<Entry>(module,"boom_entry");
            var context=new Context();IntPtr wrong=create(heap,layout(boxId),ref context);if(wrong==IntPtr.Zero||context.Kind!=0)throw new Exception("Receiver allocation failed");
            context=new Context();if(entry(ref context,new ulong[]{unchecked((ulong)wrong.ToInt64())})!=0||context.Kind!=7||context.PC!=1||context.Method!=entryId||context.Depth!=0)throw new Exception("Different named class was accepted as receiver");
            context=new Context();IntPtr right=create(heap,layout(nodeId),ref context);if(right==IntPtr.Zero||context.Kind!=0)throw new Exception("Receiver allocation failed");
            context=new Context();entry(ref context,new ulong[]{unchecked((ulong)right.ToInt64())});if(context.Kind!=4||context.PC!=4||context.Method!=entryId||context.Depth!=0)throw new Exception("Null nested field error precedence changed");
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
