using System;
using System.Runtime.InteropServices;
public static class BoomStringProgramProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint owner,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Descriptor(uint owner);
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
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("String heap binding failed");
            const int count=4099;var values=new long[count*16];for(int i=0;i<count;i++){values[i*16]=i;values[i*16+1]=i*37;}
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("String pool worker creation failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Cold String literal run failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=(expectedHash^(uint)i^(uint)(i*37))||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Cold String publication mismatch "+i);
            uint rootCount;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out rootCount);
            if(rootCount!=1||Marshal.ReadInt64(heap,56)!=2)throw new Exception("Literal was allocated more than once");
            IntPtr value=Marshal.ReadIntPtr(roots),chars=Marshal.ReadIntPtr(value);
            if(Marshal.ReadInt64(value,-16)!=16||Marshal.ReadInt32(value,-20)!=1||Marshal.ReadInt64(chars,-8)!=261||Marshal.ReadInt64(chars,-16)!=10||unchecked((uint)Marshal.ReadInt32(value,8))!=expectedHash||Marshal.ReadInt32(value,12)!=1)throw new Exception("String payload/hash publication failed");
            var collect=Symbol<Collect>(module,"boom_heap_collect");
            if(collect(heap,roots,rootCount)!=0||Marshal.ReadInt64(heap,56)!=2)throw new Exception("Interned literal graph was collected");
            var context=new Context();ulong result=Symbol<Entry>(module,"boom_entry")(ref context,new ulong[]{0,0});
            if(context.Kind!=0||result!=expectedHash||Marshal.ReadInt64(heap,56)!=2||Marshal.ReadIntPtr(roots)!=value)throw new Exception("Literal identity changed after collection");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
    public static void Constants(string dll,uint owner,uint constant,uint text,uint alias,uint table) {
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try {
            heap=Symbol<HeapCreate>(module,"boom_heap_create")(1024*1024);if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Constant String heap failed");
            var entry=Symbol<Entry>(module,"boom_entry");var context=new Context();entry(ref context,new ulong[]{0});if(context.Kind!=0)throw new Exception("Constant String initializer failed");
            var field=Symbol<Field>(module,"boom_get_static_field");IntPtr value=Marshal.ReadIntPtr(field(owner,constant));
            if(value==IntPtr.Zero||Marshal.ReadIntPtr(field(owner,text))!=value||Marshal.ReadIntPtr(field(owner,alias))!=value)throw new Exception("String ConstantValue was not prepared/interned");
            IntPtr chars=Marshal.ReadIntPtr(value);ushort[] units={0x4e16,0x754c,0xd83d,0xde80};
            for(int i=0;i<units.Length;i++)if(unchecked((ushort)Marshal.ReadInt16(chars,i*2))!=units[i])throw new Exception("Constant UTF16 content changed");
            context=new Context();if(entry(ref context,new ulong[]{5})!=2112||context.Kind!=0)throw new Exception("Aa hash mismatch");
            context=new Context();if(entry(ref context,new ulong[]{6})!=2112||context.Kind!=0)throw new Exception("BB hash mismatch");
            IntPtr strings=Marshal.ReadIntPtr(field(owner,table));if(Marshal.ReadIntPtr(strings,40)==Marshal.ReadIntPtr(strings,48))throw new Exception("Equal hash values merged different strings");
            uint count;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out count);
            if(count!=12||Symbol<Collect>(module,"boom_heap_collect")(heap,roots,count)!=0||Marshal.ReadInt64(heap,56)!=17)throw new Exception("Constant/literal/array roots were not retained");
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
    public static void AbiAndFailure(string runtime) {
        IntPtr library=Open(runtime),heap=IntPtr.Zero,otherHeap=IntPtr.Zero,pool=IntPtr.Zero,roots=IntPtr.Zero,entry=IntPtr.Zero,layout=IntPtr.Zero,chars=IntPtr.Zero;
        try {
            var create=Symbol<HeapCreate>(library,"boom_heap_create");var collect=Symbol<Collect>(library,"boom_heap_collect");var load=Symbol<Load>(library,"boom_string_load");var intrinsic=Symbol<Intrinsic>(library,"boom_string_intrinsic");
            heap=create(4096);otherHeap=create(4096);if(heap==IntPtr.Zero||otherHeap==IntPtr.Zero)throw new Exception("Small String heaps failed");
            pool=Marshal.AllocHGlobal(56);roots=Marshal.AllocHGlobal(8);entry=Marshal.AllocHGlobal(16);layout=Marshal.AllocHGlobal(24);chars=Marshal.AllocHGlobal(1545*2);
            Marshal.Copy(new long[7],0,pool,7);Marshal.WriteIntPtr(roots,IntPtr.Zero);Marshal.Copy(new long[2],0,entry,2);Marshal.Copy(new long[3],0,layout,3);
            var units=new short[1545];units[0]=65;units[1]=0;units[2]=unchecked((short)0xd800);Marshal.Copy(units,0,chars,units.Length);
            Marshal.WriteInt32(pool,0,0x53545250);Marshal.WriteInt32(pool,4,2);Marshal.WriteInt32(pool,16,1);Marshal.WriteIntPtr(pool,24,roots);Marshal.WriteIntPtr(pool,32,entry);Marshal.WriteIntPtr(pool,40,layout);
            Marshal.WriteIntPtr(entry,chars);Marshal.WriteInt32(entry,8,1545);Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,1);Marshal.WriteInt64(layout,8,16);Marshal.WriteInt32(layout,16,1);Marshal.WriteInt32(layout,20,2);
            var context=new Context();if(load(heap,pool,0,ref context)!=IntPtr.Zero||context.Kind!=3||Marshal.ReadInt32(pool,8)!=0||Marshal.ReadIntPtr(roots)!=IntPtr.Zero||Marshal.ReadInt64(heap,56)!=1)throw new Exception("Partially allocated String failure did not release its lock/root");
            context=new Context();if(load(otherHeap,pool,0,ref context)!=IntPtr.Zero||context.Kind!=7||Marshal.ReadInt32(pool,8)!=0||Marshal.ReadInt64(otherHeap,56)!=0)throw new Exception("String pool accepted another heap");
            if(collect(heap,IntPtr.Zero,0)!=1||Marshal.ReadInt64(heap,56)!=0)throw new Exception("Failed String partial allocation leaked");
            Marshal.WriteInt32(entry,8,3);context=new Context();IntPtr value=load(heap,pool,0,ref context);
            if(value==IntPtr.Zero||context.Kind!=0||Marshal.ReadIntPtr(roots)!=value||Marshal.ReadInt64(heap,56)!=2)throw new Exception("String pool could not recover after quiescent GC");
            context=new Context();if(load(heap,pool,0,ref context)!=value||context.Kind!=0||Marshal.ReadInt64(heap,56)!=2)throw new Exception("Cached String was allocated again");
            context=new Context();if(intrinsic(ref context,new ulong[]{unchecked((ulong)value.ToInt64()),2},pool,2)!=0xd800||context.Kind!=0)throw new Exception("UTF16 surrogate was not preserved");
            context=new Context();intrinsic(ref context,new ulong[]{unchecked((ulong)value.ToInt64()),3},pool,2);if(context.Kind!=11)throw new Exception("String bounds error kind incorrect");
            Marshal.WriteInt32(pool,4,1);context=new Context();if(load(heap,pool,0,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Old pool ABI accepted");Marshal.WriteInt32(pool,4,2);
            context=new Context();if(load(heap,pool,1,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Out-of-range literal id accepted");
            context=new Context();intrinsic(ref context,new ulong[]{unchecked((ulong)value.ToInt64())},pool,255);if(context.Kind!=7)throw new Exception("Invalid String operation accepted");
            if(collect(heap,roots,1)!=0||Marshal.ReadInt64(heap,56)!=2)throw new Exception("Recovered String roots failed");
        }finally{if(otherHeap!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(otherHeap);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(heap);foreach(var pointer in new[]{pool,roots,entry,layout,chars})if(pointer!=IntPtr.Zero)Marshal.FreeHGlobal(pointer);FreeLibrary(library);}
    }
    public static string[] FailedInitializer(string dll,uint owner,uint initializer) {
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try {
            heap=Symbol<HeapCreate>(module,"boom_heap_create")(1024*1024);if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Failed String class heap failed");
            var entry=Symbol<Entry>(module,"boom_entry");var context=new Context();entry(ref context,new ulong[0]);
            if(context.Kind!=8||context.Depth!=0)throw new Exception("String initializer failure was not wrapped");
            IntPtr descriptor=Symbol<Descriptor>(module,"boom_get_class_descriptor")(owner);
            if(Marshal.ReadInt32(descriptor,8)!=3||Marshal.ReadInt32(descriptor,12)!=0||Marshal.ReadInt32(descriptor,32)!=11||unchecked((uint)Marshal.ReadInt32(descriptor,40))!=initializer)throw new Exception("Original String exception was lost");
            uint count;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out count);
            if(count!=3||Symbol<Collect>(module,"boom_heap_collect")(heap,roots,count)!=0||Marshal.ReadInt64(heap,56)!=2)throw new Exception("Failed class lost its prepared String roots");
            context=new Context();entry(ref context,new ulong[0]);if(context.Kind!=9||context.Depth!=0)throw new Exception("Failed String initializer was replayed");
            return new[]{"e java.lang.ExceptionInInitializerError","e java.lang.NoClassDefFoundError"};
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
}
