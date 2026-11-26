using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Threading;

// Test host only. The allocator, publication, conversion, and heap are assembly.
public static class BoomJavaStringLiteralProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Literal(IntPtr context,IntPtr pool,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate ulong Body(IntPtr context,IntPtr arguments);
    private sealed class Row {
        public string Key; public ushort[] Units; public uint Hash; public byte Coder; public byte[] Bytes;
    }
    private sealed class Pool : IDisposable {
        public IntPtr Heap,Header,Roots,States,Entries,Layout;
        public readonly Row[] Rows;
        private readonly Destroy destroy;
        private readonly List<IntPtr> blocks=new List<IntPtr>();
        public IntPtr Block(int size) { IntPtr p=Marshal.AllocHGlobal(Math.Max(1,size)); blocks.Add(p); for(int i=0;i<size;i++) Marshal.WriteByte(p,i,0); return p; }
        public Pool(Create create,Destroy release,Row[] rows,bool compact,ulong budget,bool paged) {
            destroy=release; Rows=rows; Heap=create(budget); if(Heap==IntPtr.Zero)throw new Exception("Heap creation failed");
            Header=Block(80);Roots=Block(rows.Length*16);States=Block(rows.Length*4);Entries=Block(rows.Length*16);Layout=Block(24);
            Marshal.WriteInt32(Layout,unchecked((int)0x4f424a43));Marshal.WriteInt32(Layout,4,2);
            Marshal.WriteInt64(Layout,8,14);Marshal.WriteInt32(Layout,16,1);Marshal.WriteInt32(Layout,20,4);
            Marshal.WriteInt32(Header,unchecked((int)0x4a534c50));Marshal.WriteInt32(Header,4,1);
            Marshal.WriteInt32(Header,8,rows.Length);Marshal.WriteInt32(Header,12,compact?1:0);
            if(paged) {
                int count=(rows.Length+255)/256;IntPtr pages=Block(count*8);
                for(int i=0;i<count;i++)Marshal.WriteIntPtr(pages,i*8,IntPtr.Add(Entries,i*256*16));
                Marshal.WriteIntPtr(Header,16,pages);Marshal.WriteInt32(Header,72,1);
            } else Marshal.WriteIntPtr(Header,16,Entries);
            Marshal.WriteIntPtr(Header,24,Roots);Marshal.WriteIntPtr(Header,32,States);
            Marshal.WriteIntPtr(Header,40,Layout);Marshal.WriteInt32(Header,48,0);Marshal.WriteInt32(Header,52,12);
            Marshal.WriteInt32(Header,56,8);Marshal.WriteInt32(Header,60,13);Marshal.WriteIntPtr(Header,64,Heap);
            for(int i=0;i<rows.Length;i++) {
                Row r=rows[i];IntPtr text=Block(r.Units.Length*2);
                for(int n=0;n<r.Units.Length;n++)Marshal.WriteInt16(text,n*2,unchecked((short)r.Units[n]));
                Marshal.WriteIntPtr(Entries,i*16,text);Marshal.WriteInt32(Entries,i*16+8,r.Units.Length);
                Marshal.WriteInt32(Entries,i*16+12,unchecked((int)r.Hash));
            }
        }
        public void Dispose() { if(Heap!=IntPtr.Zero){destroy(Heap);Heap=IntPtr.Zero;} foreach(IntPtr block in blocks)Marshal.FreeHGlobal(block); }
    }
    private static IntPtr Context() { IntPtr p=Marshal.AllocHGlobal(32);for(int i=0;i<32;i++)Marshal.WriteByte(p,i,0);return p; }
    private static byte[] Hex(string text) { byte[] v=new byte[text.Length/2];for(int i=0;i<v.Length;i++)v[i]=byte.Parse(text.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);return v; }
    private static Row[] Read(string oracle) {
        var unique=new Dictionary<string,Row>(StringComparer.Ordinal);
        foreach(string line in File.ReadLines(oracle)) {
            string[] p=line.Split('\t');if(p.Length!=4)throw new Exception("Bad oracle record");
            if(unique.ContainsKey(p[0]))continue;
            ushort[] units=new ushort[p[0].Length/4];for(int i=0;i<units.Length;i++)units[i]=ushort.Parse(p[0].Substring(i*4,4),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
            unique.Add(p[0],new Row{Key=p[0],Units=units,Coder=byte.Parse(p[1]),Hash=uint.Parse(p[2],NumberStyles.HexNumber,CultureInfo.InvariantCulture),Bytes=Hex(p[3])});
        }
        Row[] rows=new Row[unique.Count];unique.Values.CopyTo(rows,0);return rows;
    }
    private static void Check(IntPtr value,IntPtr context,Pool pool,int index) {
        CheckObject(value,context,pool.Layout,pool.Roots,pool.States,pool.Rows[index],index);
    }
    private static void CheckObject(IntPtr value,IntPtr context,IntPtr layout,IntPtr roots,IntPtr states,Row row,int index) {
        if(value==IntPtr.Zero||Marshal.ReadInt32(context)!=0)throw new Exception("Literal error at "+index+": "+Marshal.ReadInt32(context));
        if(Marshal.ReadIntPtr(value,-8)!=layout||Marshal.ReadInt64(value,-16)!=14||Marshal.ReadInt32(value,-20)!=1)throw new Exception("Wrong Java String layout");
        if(Marshal.ReadByte(value,12)!=row.Coder||unchecked((uint)Marshal.ReadInt32(value,8))!=row.Hash||Marshal.ReadByte(value,13)!=(row.Hash==0?1:0))throw new Exception("String scalar fields differ at "+index);
        IntPtr bytes=Marshal.ReadIntPtr(value);if(Marshal.ReadInt64(bytes,-8)!=264||Marshal.ReadInt64(bytes,-16)!=row.Bytes.Length||Marshal.ReadInt32(bytes,-20)!=0)throw new Exception("Wrong byte[] shape");
        for(int i=0;i<row.Bytes.Length;i++)if(Marshal.ReadByte(bytes,i)!=row.Bytes[i])throw new Exception("String bytes differ at "+index+"/"+i);
        if(Marshal.ReadIntPtr(roots,index*16)!=value||Marshal.ReadIntPtr(roots,index*16+8)!=IntPtr.Zero||Marshal.ReadInt32(states,index*4)!=2)throw new Exception("Literal publication differs");
    }
    public static long[] RunGenerated(string runtime,string kernel,string oracle,string aliases,string valueSymbol,string emptySymbol) {
        IntPtr native=NativeLibrary.Load(runtime),module=IntPtr.Zero,heap=IntPtr.Zero,other=IntPtr.Zero;
        Destroy destroy=Marshal.GetDelegateForFunctionPointer<Destroy>(NativeLibrary.GetExport(native,"boom_heap_destroy"));
        try {
            module=NativeLibrary.Load(kernel);
            Create create=Marshal.GetDelegateForFunctionPointer<Create>(NativeLibrary.GetExport(native,"boom_heap_create"));
            Collect collect=Marshal.GetDelegateForFunctionPointer<Collect>(NativeLibrary.GetExport(native,"boom_heap_collect"));
            Literal literal=Marshal.GetDelegateForFunctionPointer<Literal>(NativeLibrary.GetExport(module,"boom_java_string_literal"));
            Bind bind=Marshal.GetDelegateForFunctionPointer<Bind>(NativeLibrary.GetExport(module,"boom_java_string_literals_bind_heap"));
            Body valueBody=Marshal.GetDelegateForFunctionPointer<Body>(NativeLibrary.GetExport(module,valueSymbol));
            Body emptyBody=Marshal.GetDelegateForFunctionPointer<Body>(NativeLibrary.GetExport(module,emptySymbol));
            IntPtr pool=NativeLibrary.GetExport(module,"boom_java_string_literal_pool");
            IntPtr roots=Marshal.ReadIntPtr(pool,24),states=Marshal.ReadIntPtr(pool,32),layout=Marshal.ReadIntPtr(pool,40);
            Row[] rows=Read(oracle);if(rows.Length!=Marshal.ReadInt32(pool,8))throw new Exception("Generated pool count differs");
            ulong required=1024*1024;foreach(Row row in rows)required+=(ulong)(((row.Bytes.Length+47L)&~15L)+48);
            // create() reserves both the object arena (4/5) and mark worklist (1/5).
            ulong budget=(((required*5+3)/4)+128+4095)&~4095UL;
            heap=create(budget);other=create(4096);if(heap==IntPtr.Zero||other==IntPtr.Zero)throw new Exception("Generated pool heap creation failed");
            if(unchecked((ulong)Marshal.ReadInt64(heap,16))<required)throw new Exception("Probe reservation does not cover the object arena");
            if(bind(IntPtr.Zero)!=0||bind(heap)!=1||bind(heap)!=1||bind(other)!=0||Marshal.ReadIntPtr(pool,64)!=heap)throw new Exception("Heap binding lifetime guard failed");
            IntPtr[] objects=new IntPtr[rows.Length];
            Parallel.For(0,8,worker=>{
                IntPtr ctx=Context(),args=Marshal.AllocHGlobal(8);
                try{for(int i=worker;i<rows.Length;i+=8){
                    IntPtr value=literal(ctx,pool,(uint)i);objects[i]=value;CheckObject(value,ctx,layout,roots,states,rows[i],i);
                    Marshal.WriteIntPtr(args,value);
                    if(valueBody(ctx,args)!=unchecked((ulong)Marshal.ReadIntPtr(value).ToInt64())||Marshal.ReadInt32(ctx)!=0)throw new Exception("Original String.value Java body differs");
                    if(emptyBody(ctx,args)!=(rows[i].Units.Length==0?1UL:0UL)||Marshal.ReadInt32(ctx)!=0||Marshal.ReadInt32(ctx,12)!=0)throw new Exception("Original String.isEmpty Java body differs");
                }}finally{Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(ctx);}
            });
            long allocated=Marshal.ReadInt64(heap,48),aliasCalls=0;
            foreach(string line in File.ReadLines(aliases)) {
                string[] fields=line.Split('\t');uint index=uint.Parse(fields[1]);
                Body alias=Marshal.GetDelegateForFunctionPointer<Body>(NativeLibrary.GetExport(module,fields[0]));
                Parallel.For(0,8,worker=>{IntPtr ctx=Context();try{if(alias(ctx,IntPtr.Zero)!=unchecked((ulong)objects[index].ToInt64())||Marshal.ReadInt32(ctx)!=0)throw new Exception("Source alias canonical identity differs");}finally{Marshal.FreeHGlobal(ctx);}});
                aliasCalls+=8;GC.KeepAlive(alias);
            }
            if(Marshal.ReadInt64(heap,48)!=allocated)throw new Exception("Source alias cache allocated guest objects");
            if(collect(heap,roots,(ulong)rows.Length*2)!=0)throw new Exception("Generated pool roots lost Java String graph");
            IntPtr context=Context();try{for(int i=0;i<rows.Length;i++)if(literal(context,pool,(uint)i)!=objects[i])throw new Exception("Generated canonical identity changed after explicit GC");}finally{Marshal.FreeHGlobal(context);}
            GC.KeepAlive(create);GC.KeepAlive(collect);GC.KeepAlive(literal);GC.KeepAlive(bind);GC.KeepAlive(valueBody);GC.KeepAlive(emptyBody);
            return new long[]{rows.Length,rows.Length*2L+aliasCalls,rows.Length*2L,aliasCalls,allocated,8};
        } finally {if(other!=IntPtr.Zero)destroy(other);if(heap!=IntPtr.Zero)destroy(heap);if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(native);GC.KeepAlive(destroy);}
    }
    public static long[] Run(string runtime,string kernel,string oracle,bool compact,bool paged) {
        IntPtr native=NativeLibrary.Load(runtime),module=IntPtr.Zero;
        try {
            module=NativeLibrary.Load(kernel);
            Create create=Marshal.GetDelegateForFunctionPointer<Create>(NativeLibrary.GetExport(native,"boom_heap_create"));
            Destroy destroy=Marshal.GetDelegateForFunctionPointer<Destroy>(NativeLibrary.GetExport(native,"boom_heap_destroy"));
            Collect collect=Marshal.GetDelegateForFunctionPointer<Collect>(NativeLibrary.GetExport(native,"boom_heap_collect"));
            Literal literal=Marshal.GetDelegateForFunctionPointer<Literal>(NativeLibrary.GetExport(module,"boom_java_string_literal"));
            Row[] rows=Read(oracle);IntPtr[] results=new IntPtr[rows.Length];
            using(Pool pool=new Pool(create,destroy,rows,compact,32UL*1024*1024,paged)) {
                int longIndex=0;for(int i=1;i<rows.Length;i++)if(rows[i].Units.Length>rows[longIndex].Units.Length)longIndex=i;
                IntPtr[] raced=new IntPtr[8];using(Barrier barrier=new Barrier(8)) {
                    Task[] tasks=new Task[8];for(int worker=0;worker<8;worker++){int slot=worker;tasks[worker]=Task.Factory.StartNew(()=>{
                        IntPtr ctx=Context();try{barrier.SignalAndWait();raced[slot]=literal(ctx,pool.Header,(uint)longIndex);Check(raced[slot],ctx,pool,longIndex);}finally{Marshal.FreeHGlobal(ctx);}
                    },CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);}
                    if(!Task.WaitAll(tasks,30000))throw new Exception("Cold literal publication timed out");
                }
                for(int i=1;i<8;i++)if(raced[i]!=raced[0])throw new Exception("Cold literal race returned different objects");
                long expected=((rows[longIndex].Bytes.Length+47L)&~15L)+48;
                if(Marshal.ReadInt64(pool.Heap,48)!=expected)throw new Exception("Cold literal race allocated duplicates");
                Parallel.For(0,8,worker=>{IntPtr ctx=Context();try{for(int i=worker;i<rows.Length;i+=8){results[i]=literal(ctx,pool.Header,(uint)i);Check(results[i],ctx,pool,i);}}finally{Marshal.FreeHGlobal(ctx);}});
                long allocated=Marshal.ReadInt64(pool.Heap,48);
                Parallel.For(0,8,worker=>{IntPtr ctx=Context();try{for(int i=0;i<rows.Length;i++){if(literal(ctx,pool.Header,(uint)i)!=results[i]||Marshal.ReadInt32(ctx)!=0)throw new Exception("Canonical literal identity changed");}}finally{Marshal.FreeHGlobal(ctx);}});
                if(Marshal.ReadInt64(pool.Heap,48)!=allocated)throw new Exception("Hot literal lookup allocated");
                if(collect(pool.Heap,pool.Roots,(ulong)rows.Length*2)!=0)throw new Exception("Literal graph was not rooted");
                IntPtr context=Context();try {
                    for(int i=0;i<rows.Length;i++)Check(literal(context,pool.Header,(uint)i),context,pool,i);
                    if(literal(context,pool.Header,uint.MaxValue)!=IntPtr.Zero||Marshal.ReadInt32(context)!=5)throw new Exception("Literal index guard failed");
                    Marshal.WriteInt32(context,0);Marshal.WriteInt32(pool.Header,52,8);
                    if(literal(context,pool.Header,0)!=IntPtr.Zero||Marshal.ReadInt32(context)!=7)throw new Exception("Overlapping String fields accepted");
                    Marshal.WriteInt32(pool.Header,52,12);Marshal.WriteInt32(context,3);Marshal.WriteInt32(context,4,123);Marshal.WriteInt32(context,8,456);
                    if(literal(context,IntPtr.Zero,0)!=IntPtr.Zero||Marshal.ReadInt32(context)!=3||Marshal.ReadInt32(context,4)!=123||Marshal.ReadInt32(context,8)!=456)throw new Exception("Pending exception changed");
                } finally {Marshal.FreeHGlobal(context);}
            }
            Row example=null;foreach(Row row in rows)if(row.Units.Length==2&&row.Bytes.Length<=4){example=row;break;}
            if(example==null)throw new Exception("Missing OOM fixture");
            using(Pool pool=new Pool(create,destroy,new Row[]{example},compact,4096,paged)) {
                IntPtr context=Context();try {
                    long budget=Marshal.ReadInt64(pool.Heap,16);Marshal.WriteInt64(pool.Heap,16,0);
                    if(literal(context,pool.Header,0)!=IntPtr.Zero||Marshal.ReadInt32(context)!=3||Marshal.ReadInt32(pool.States)!=0)throw new Exception("First allocation OOM failed");
                    Marshal.WriteInt32(context,0);Marshal.WriteInt64(pool.Heap,16,48);
                    if(literal(context,pool.Header,0)!=IntPtr.Zero||Marshal.ReadInt32(context)!=3||Marshal.ReadInt32(pool.States)!=0||Marshal.ReadIntPtr(pool.Roots,8)!=IntPtr.Zero)throw new Exception("Partial allocation OOM failed");
                    Marshal.WriteInt64(pool.Heap,16,budget);
                    if(collect(pool.Heap,pool.Roots,2)!=1)throw new Exception("Abandoned temporary byte[] was retained");
                    Marshal.WriteInt32(context,0);Check(literal(context,pool.Header,0),context,pool,0);
                } finally{Marshal.FreeHGlobal(context);}
            }
            GC.KeepAlive(create);GC.KeepAlive(destroy);GC.KeepAlive(collect);GC.KeepAlive(literal);
            return new long[]{rows.Length,rows.Length*10L+8,8};
        } finally {if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(native);}
    }
}
