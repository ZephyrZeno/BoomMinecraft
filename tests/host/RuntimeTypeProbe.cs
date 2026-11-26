using System;
using System.Runtime.InteropServices;
public static class BoomRuntimeTypeProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr heap,int count,uint kind,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Query(IntPtr value,IntPtr map,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Check(IntPtr value,IntPtr map,IntPtr target,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong GetClass(ref Context context,[In] ulong[] args,IntPtr heap,IntPtr map);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {var p=GetProcAddress(module,name);if(p==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string file){var m=LoadLibraryExW(file,IntPtr.Zero,0x1100);if(m==IntPtr.Zero)throw new Exception("Cannot load "+file);return m;}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static void Type(IntPtr p,int kind,int flags,IntPtr parent,IntPtr ancestors,int count){Marshal.WriteInt32(p,0,0x54595045);Marshal.WriteInt32(p,4,1);Marshal.WriteInt32(p,8,kind);Marshal.WriteInt32(p,12,flags);Marshal.WriteIntPtr(p,16,parent);Marshal.WriteIntPtr(p,24,ancestors);Marshal.WriteInt32(p,32,count);}
    public static void AbiAndFailure(string runtime){
        IntPtr library=Open(runtime),heap=IntPtr.Zero,data=IntPtr.Zero;
        try {
            heap=Symbol<HeapCreate>(library,"boom_heap_create")(1024*1024);if(heap==IntPtr.Zero)throw new Exception("Runtime type heap failed");
            data=Marshal.AllocHGlobal(448);Marshal.Copy(new byte[448],0,data,448);
            IntPtr layout=data,obj=IntPtr.Add(data,32),node=IntPtr.Add(data,80),twin=IntPtr.Add(data,128),integer=IntPtr.Add(data,176),array=IntPtr.Add(data,224),ancestors=IntPtr.Add(data,272),map=IntPtr.Add(data,288),rows=IntPtr.Add(data,320);
            Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,1);Marshal.WriteInt64(layout,8,8);Marshal.WriteInt32(layout,20,1);
            Type(obj,1,1,IntPtr.Zero,IntPtr.Zero,0);Marshal.WriteIntPtr(ancestors,obj);Type(node,1,0,obj,ancestors,1);Type(twin,1,0,obj,ancestors,1);Type(integer,0,4,IntPtr.Zero,IntPtr.Zero,0);Type(array,3,0,integer,IntPtr.Zero,0);
            Marshal.WriteInt32(map,0,0x52545950);Marshal.WriteInt32(map,4,1);Marshal.WriteInt32(map,8,2);Marshal.WriteInt32(map,12,5);Marshal.WriteIntPtr(map,16,rows);
            Marshal.WriteIntPtr(rows,layout);Marshal.WriteIntPtr(rows,8,node);Marshal.WriteInt32(rows,16,1);Marshal.WriteInt64(rows,24,8);
            Marshal.WriteInt64(rows,40,266);Marshal.WriteIntPtr(rows,48,array);Marshal.WriteInt32(rows,56,4);Marshal.WriteInt32(rows,60,1);Marshal.WriteInt32(rows,76,2);
            var context=new Context();IntPtr value=Symbol<Make>(library,"boom_object_new")(heap,layout,ref context);
            var query=Symbol<Query>(library,"boom_runtime_type");var cast=Symbol<Check>(library,"boom_runtime_cast");var instance=Symbol<Check>(library,"boom_runtime_instanceof");
            if(value==IntPtr.Zero||context.Kind!=0)throw new Exception("Type-check object setup failed");
            context=new Context();if(query(value,map,ref context)!=node||context.Kind!=0)throw new Exception("Heap tag did not preserve type identity");
            context=new Context();if(cast(value,map,obj,ref context)!=Bits(value)||context.Kind!=0)throw new Exception("Cast to actual ancestor failed");
            context=new Context();if(instance(value,map,node,ref context)!=1||context.Kind!=0)throw new Exception("Exact instanceof failed");
            context=new Context();if(instance(value,map,twin,ref context)!=0||context.Kind!=0)throw new Exception("Shape-equal type descriptors were conflated");
            context=new Context();if(cast(value,map,twin,ref context)!=0||context.Kind!=12)throw new Exception("Wrong-class cast did not report ClassCastException");
            context=new Context();if(cast(IntPtr.Zero,map,node,ref context)!=0||context.Kind!=0)throw new Exception("Null checkcast must succeed");
            context=new Context();if(instance(IntPtr.Zero,map,node,ref context)!=0||context.Kind!=0)throw new Exception("Null instanceof must be false");
            context=new Context();query(IntPtr.Zero,map,ref context);if(context.Kind!=4)throw new Exception("Null getClass query must fail");
            context=new Context();cast(value,map,integer,ref context);if(context.Kind!=7)throw new Exception("Primitive type was accepted as reference cast target");
            Marshal.WriteInt32(map,4,2);context=new Context();instance(value,map,node,ref context);if(context.Kind!=7)throw new Exception("Incompatible map ABI was accepted");Marshal.WriteInt32(map,4,1);
            Marshal.WriteInt32(rows,16,5);context=new Context();query(value,map,ref context);if(context.Kind!=7)throw new Exception("Out-of-range mapped type ID was accepted");Marshal.WriteInt32(rows,16,1);
            Marshal.WriteInt64(rows,24,16);context=new Context();query(value,map,ref context);if(context.Kind!=7)throw new Exception("Mismatched object layout size was accepted");Marshal.WriteInt64(rows,24,8);
            IntPtr unknown=Symbol<Alloc>(library,"boom_heap_alloc")(heap,8,0,new IntPtr(1));context=new Context();query(unknown,map,ref context);if(context.Kind!=7)throw new Exception("Unregistered heap tag was accepted");
            context=new Context();IntPtr primitive=Symbol<ArrayNew>(library,"boom_array_new")(heap,3,10,ref context);
            context=new Context();if(query(primitive,map,ref context)!=array||context.Kind!=0)throw new Exception("Primitive array type query failed");
            context=new Context();if(cast(primitive,map,obj,ref context)!=Bits(primitive)||context.Kind!=0)throw new Exception("Array-to-Object cast failed");
            Marshal.WriteInt64(primitive,-16,13);context=new Context();query(primitive,map,ref context);if(context.Kind!=7)throw new Exception("Misaligned primitive array payload was accepted");Marshal.WriteInt64(primitive,-16,12);
            context=new Context();Symbol<GetClass>(library,"boom_runtime_getclass")(ref context,new[]{Bits(value)},heap,map);if(context.Kind!=7)throw new Exception("Missing mirror pool was accepted");
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(heap);if(data!=IntPtr.Zero)Marshal.FreeHGlobal(data);FreeLibrary(library);}
    }
    public static void Cold(string dll,string runtime){
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Cold getClass heap failed");
            const int count=4099;var values=new long[count*16];input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("Cold getClass workers failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Cold getClass execution failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=1||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Cold getClass identity/context mismatch");
            uint rootCount;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out rootCount);
            if(rootCount==0||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Class mirror/literal was created more than once");
            if(Symbol<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)!=0||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Class/string graph was lost during GC");
            var context=new Context();if(Symbol<Entry>(module,"boom_entry")(ref context,new ulong[]{0})!=1||context.Kind!=0||Marshal.ReadInt64(heap,56)!=3)throw new Exception("getClass identity changed after collection");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
