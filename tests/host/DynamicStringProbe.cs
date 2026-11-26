using System;
using System.Runtime.InteropServices;
public static class BoomDynamicStringProbe {
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
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr heap,IntPtr pool,uint value,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr pool,int length,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Intrinsic(ref Context context,[In] ulong[] args,IntPtr pool,uint operation);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {var address=GetProcAddress(module,name);if(address==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(address);}
    static IntPtr Open(string path){var module=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(module==IntPtr.Zero)throw new Exception("Cannot open "+path);return module;}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    sealed class PoolData:IDisposable {
        public IntPtr Pool,Roots,Entries,Layout,Chars;
        static IntPtr Zero(int bytes){IntPtr p=Marshal.AllocHGlobal(bytes);Marshal.Copy(new byte[bytes],0,p,bytes);return p;}
        public PoolData(){
            Pool=Zero(80);Roots=Zero(24);Entries=Zero(16);Layout=Zero(24);Chars=Zero(6);
            Marshal.WriteInt16(Chars,0,65);Marshal.WriteInt16(Chars,2,0);Marshal.WriteInt16(Chars,4,unchecked((short)0xd800));
            Marshal.WriteInt32(Pool,0,0x53545250);Marshal.WriteInt32(Pool,4,3);Marshal.WriteInt32(Pool,16,1);Marshal.WriteIntPtr(Pool,24,Roots);Marshal.WriteIntPtr(Pool,32,Entries);Marshal.WriteIntPtr(Pool,40,Layout);Marshal.WriteIntPtr(Pool,64,IntPtr.Add(Roots,8));
            Marshal.WriteIntPtr(Entries,Chars);Marshal.WriteInt32(Entries,8,3);
            Marshal.WriteInt32(Layout,0,0x4f424a43);Marshal.WriteInt32(Layout,4,1);Marshal.WriteInt64(Layout,8,16);Marshal.WriteInt32(Layout,16,1);Marshal.WriteInt32(Layout,20,2);
        }
        public void Dispose(){foreach(var p in new[]{Pool,Roots,Entries,Layout,Chars})Marshal.FreeHGlobal(p);}
    }
    static IntPtr Value(Make make,IntPtr heap,PoolData data,params ushort[] units){
        var context=new Context();IntPtr value=make(heap,data.Pool,units.Length,ref context);
        if(value==IntPtr.Zero||context.Kind!=0)throw new Exception("Dynamic String allocation failed");
        IntPtr chars=Marshal.ReadIntPtr(value);for(int i=0;i<units.Length;i++)Marshal.WriteInt16(chars,i*2,unchecked((short)units[i]));return value;
    }
    public static void AbiAndFailure(string runtime){
        IntPtr library=Open(runtime),heap=IntPtr.Zero,other=IntPtr.Zero;
        try {
            var create=Symbol<HeapCreate>(library,"boom_heap_create");var destroy=Symbol<HeapDestroy>(library,"boom_heap_destroy");
            var make=Symbol<Make>(library,"boom_string_allocate");var load=Symbol<Load>(library,"boom_string_load");
            var intrinsic=Symbol<Intrinsic>(library,"boom_string_intrinsic");var collect=Symbol<Collect>(library,"boom_heap_collect");
            var alloc=Symbol<Alloc>(library,"boom_heap_alloc");
            heap=create(1024*1024);other=create(1024*1024);if(heap==IntPtr.Zero||other==IntPtr.Zero)throw new Exception("Dynamic String heaps failed");
            using(var data=new PoolData()){
                IntPtr first=Value(make,heap,data,65,0,0xd800),second=Value(make,heap,data,65,0,0xd800);
                if(first==second)throw new Exception("Dynamic Strings were implicitly interned");
                var context=new Context();if(intrinsic(ref context,new[]{Bits(first)},data.Pool,7)!=Bits(first)||context.Kind!=0)throw new Exception("First intern did not adopt receiver");
                context=new Context();if(load(heap,data.Pool,0,ref context)!=first||context.Kind!=0)throw new Exception("Later ldc did not use adopted literal");
                context=new Context();if(intrinsic(ref context,new[]{Bits(second)},data.Pool,7)!=Bits(first)||context.Kind!=0)throw new Exception("Equal dynamic/literal content did not merge");
                if(Marshal.ReadIntPtr(data.Roots)!=first||Marshal.ReadInt32(data.Pool,60)!=0)throw new Exception("Literal adoption incorrectly used dynamic table");
                for(int i=0;i<200;i++){
                    IntPtr value=Value(make,heap,data,68,(ushort)i),duplicate=Value(make,heap,data,68,(ushort)i);
                    context=new Context();if(intrinsic(ref context,new[]{Bits(value)},data.Pool,7)!=Bits(value)||context.Kind!=0)throw new Exception("New dynamic value was not canonical");
                    context=new Context();if(intrinsic(ref context,new[]{Bits(duplicate)},data.Pool,7)!=Bits(value)||context.Kind!=0)throw new Exception("Dynamic table lookup changed content/identity");
                }
                if(Marshal.ReadInt32(data.Pool,60)!=200||Marshal.ReadInt32(data.Pool,72)!=512)throw new Exception("Intern table failed to grow");
                if(collect(heap,data.Roots,2)==ulong.MaxValue||Marshal.ReadInt64(heap,56)!=403)throw new Exception("Growable table graph was not retained by GC");
                IntPtr table=Marshal.ReadIntPtr(data.Roots,8);if(Marshal.ReadInt32(table,-20)!=512)throw new Exception("Intern table did not expose all GC reference slots");
                var seen=new bool[200];var identities=new IntPtr[200];int occupied=0;
                for(int i=0;i<512;i++){
                    IntPtr value=Marshal.ReadIntPtr(table,i*8);if(value==IntPtr.Zero)continue;
                    IntPtr chars=Marshal.ReadIntPtr(value);int index=unchecked((ushort)Marshal.ReadInt16(chars,2));
                    if(Marshal.ReadInt16(chars)!=68||index>=200||seen[index])throw new Exception("Intern table content changed after collection");seen[index]=true;identities[index]=value;occupied++;
                }
                if(occupied!=200)throw new Exception("Rehashed intern values were lost");
                for(int i=0;i<200;i++){
                    IntPtr duplicate=Value(make,heap,data,68,(ushort)i);context=new Context();
                    if(intrinsic(ref context,new[]{Bits(duplicate)},data.Pool,7)!=Bits(identities[i])||context.Kind!=0)throw new Exception("Rehashed lookup lost canonical identity after GC");
                }
                IntPtr empty=Value(make,heap,data),nul=Value(make,heap,data,0);
                context=new Context();if(intrinsic(ref context,new[]{Bits(empty)},data.Pool,7)!=Bits(empty)||context.Kind!=0)throw new Exception("Empty hash-zero interning failed");
                context=new Context();if(intrinsic(ref context,new[]{Bits(nul)},data.Pool,7)!=Bits(nul)||context.Kind!=0||empty==nul)throw new Exception("Hash-zero values were conflated");
                context=new Context();make(other,data.Pool,1,ref context);if(context.Kind!=7||Marshal.ReadInt64(other,56)!=0)throw new Exception("Dynamic pool accepted another heap");
                context=new Context();make(heap,data.Pool,-1,ref context);if(context.Kind!=2)throw new Exception("Negative String buffer length was accepted");
                Marshal.WriteInt32(data.Pool,72,255);context=new Context();intrinsic(ref context,new[]{Bits(first)},data.Pool,7);
                // Literal hits remain valid without consulting the independent dynamic table.
                if(context.Kind!=0)throw new Exception("Literal lookup unexpectedly touched the dynamic table");
                context=new Context();IntPtr temp=Value(make,heap,data,88);intrinsic(ref context,new[]{Bits(temp)},data.Pool,7);
                if(context.Kind!=7||Marshal.ReadInt32(data.Pool,56)!=0)throw new Exception("Corrupt intern table ABI was accepted");Marshal.WriteInt32(data.Pool,72,512);
                context=new Context();intrinsic(ref context,new ulong[]{0},data.Pool,7);if(context.Kind!=4)throw new Exception("Null intern receiver was accepted");
                Marshal.WriteInt32(data.Pool,4,2);context=new Context();make(heap,data.Pool,1,ref context);if(context.Kind!=7)throw new Exception("Dynamic allocator accepted legacy pool ABI");
            }
            destroy(heap);heap=create(4096);
            using(var data=new PoolData()){
                var context=new Context();if(make(heap,data.Pool,1545,ref context)!=IntPtr.Zero||context.Kind!=3||Marshal.ReadInt32(data.Pool,8)!=0||Marshal.ReadInt64(heap,56)!=1)throw new Exception("Partial dynamic String allocation did not fail cleanly");
                if(collect(heap,IntPtr.Zero,0)!=1)throw new Exception("Failed dynamic char buffer leaked");
                IntPtr value=Value(make,heap,data,88);Marshal.WriteIntPtr(data.Roots,16,value);
                if(alloc(heap,3040,0,new IntPtr(1))==IntPtr.Zero)throw new Exception("Intern OOM setup failed");
                context=new Context();intrinsic(ref context,new[]{Bits(value)},data.Pool,7);
                if(context.Kind!=3||Marshal.ReadInt32(data.Pool,56)!=0||Marshal.ReadIntPtr(data.Roots,8)!=IntPtr.Zero||Marshal.ReadInt32(data.Pool,60)!=0)throw new Exception("Intern OOM published a partial table or kept lock");
                if(collect(heap,data.Roots,3)!=1||Marshal.ReadInt64(heap,56)!=2)throw new Exception("Intern OOM roots were lost");
                context=new Context();if(intrinsic(ref context,new[]{Bits(value)},data.Pool,7)!=Bits(value)||context.Kind!=0||Marshal.ReadInt32(data.Pool,60)!=1)throw new Exception("Intern did not recover after quiescent GC");
            }
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(heap);if(other!=IntPtr.Zero)Symbol<HeapDestroy>(library,"boom_heap_destroy")(other);FreeLibrary(library);}
    }
    public static void Cold(string dll,string runtime){
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(16*1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Cold intern heap failed");
            const int count=4099;var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=7;
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);
            if(pool==IntPtr.Zero||Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Cold parallel intern failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=1||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Cold parallel intern identity/context mismatch");
            uint rootCount;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out rootCount);
            if(rootCount!=1||Marshal.ReadInt64(heap,56)!=count*4+1)throw new Exception("Cold intern allocation/publication count mismatch");
            IntPtr table=Marshal.ReadIntPtr(roots),canonical=IntPtr.Zero;for(int i=0;i<64;i++){IntPtr item=Marshal.ReadIntPtr(table,i*8);if(item!=IntPtr.Zero){if(canonical!=IntPtr.Zero)throw new Exception("Duplicate interned content");canonical=item;}}if(canonical==IntPtr.Zero)throw new Exception("Missing canonical String");
            if(Marshal.ReadInt32(table,-20)!=64)throw new Exception("Cold table was initialized more than once");
            var collect=Symbol<Collect>(module,"boom_heap_collect");
            if(collect(heap,roots,rootCount)!=(ulong)(count*4-2)||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Cold intern graph was lost during GC");
            var context=new Context();if(Symbol<Entry>(module,"boom_entry")(ref context,new ulong[]{7})!=1||context.Kind!=0)throw new Exception("Intern failed after collection");
            if(collect(heap,roots,rootCount)!=4||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Canonical identity changed across GC");
            bool retained=false;for(int i=0;i<64;i++)if(Marshal.ReadIntPtr(table,i*8)==canonical)retained=true;if(!retained)throw new Exception("Canonical pointer changed across GC");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
