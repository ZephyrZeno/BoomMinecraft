using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development host: stresses the assembly ABI with synthetic metadata, then
// exercises genuine assembly heap objects. This is not a game launch test.
public static class BoomIndexedTypeProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong budget);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Prepare(IntPtr map,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Query(IntPtr value,IntPtr map,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Cast(IntPtr value,IntPtr map,IntPtr target,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(IntPtr value,IntPtr ctx,IntPtr fields,IntPtr map);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint SetException(IntPtr ctx,IntPtr value,IntPtr map,IntPtr throwable);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint MatchException(IntPtr ctx,uint pc,IntPtr handlers);
    sealed class Memory:IDisposable {
        public readonly List<IntPtr> Blocks=new List<IntPtr>();
        public IntPtr New(int count) {IntPtr ptr=Marshal.AllocHGlobal(count);Blocks.Add(ptr);for(int i=0;i<count;i++)Marshal.WriteByte(ptr,i,0);return ptr;}
        public void Dispose(){foreach(IntPtr ptr in Blocks)Marshal.FreeHGlobal(ptr);}
    }
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    public static long[] Run(string runtime) {
        const int Count=131071,Capacity=200000,Slots=262144;
        IntPtr module=NativeLibrary.Load(runtime),heap=IntPtr.Zero;
        Destroy destroy=Symbol<Destroy>(module,"boom_heap_destroy");
        try {using(Memory mem=new Memory()) {
            IntPtr descriptor=mem.New(40),rows=mem.New(Count*40),slots=mem.New(Slots*8),map=mem.New(48);
            Marshal.WriteInt32(descriptor,0x54595045);Marshal.WriteInt32(descriptor,4,1);Marshal.WriteInt32(descriptor,8,1);
            for(int i=0;i<Count;i++) {
                int at=i*40;Marshal.WriteIntPtr(rows,at,new IntPtr(0x10000L+i*16L));Marshal.WriteIntPtr(rows,at+8,descriptor);
                Marshal.WriteInt32(rows,at+16,i);Marshal.WriteInt64(rows,at+24,32);Marshal.WriteInt32(rows,at+32,1);
            }
            Marshal.WriteInt32(map,0x52545950);Marshal.WriteInt32(map,4,2);Marshal.WriteInt32(map,8,Count);Marshal.WriteInt32(map,12,Capacity);
            Marshal.WriteIntPtr(map,16,rows);Marshal.WriteIntPtr(map,32,slots);Marshal.WriteInt32(map,40,Slots-1);
            Query query=Symbol<Query>(module,"boom_runtime_type"),rowQuery=Symbol<Query>(module,"boom_runtime_row");
            Prepare prepare=Symbol<Prepare>(module,"boom_runtime_index_prepare");Field field=Symbol<Field>(module,"boom_field_address");
            Alloc alloc=Symbol<Alloc>(module,"boom_heap_alloc");Cast cast=Symbol<Cast>(module,"boom_runtime_cast");
            heap=Symbol<Create>(module,"boom_heap_create")(1024*1024);Need(heap!=IntPtr.Zero,"Index test heap creation failed");
            IntPtr first=alloc(heap,32,1,new IntPtr(0x10000)),last=alloc(heap,32,1,new IntPtr(0x10000L+(Count-1)*16L));
            Need(first!=IntPtr.Zero&&last!=IntPtr.Zero,"Index test allocations failed");
            using(Barrier barrier=new Barrier(8)) {
                Task[] tasks=new Task[8];for(int n=0;n<8;n++){int worker=n;tasks[n]=Task.Factory.StartNew(()=>{
                    IntPtr ctx=Marshal.AllocHGlobal(32);try{for(int i=0;i<32;i++)Marshal.WriteByte(ctx,i,0);barrier.SignalAndWait();
                        Need(query(worker%2==0?first:last,map,ctx)==descriptor&&Marshal.ReadInt32(ctx)==0,"Concurrent cold index failed");
                    }finally{Marshal.FreeHGlobal(ctx);}},CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);}
                Need(Task.WaitAll(tasks,30000),"Cold index preparation timed out");
            }
            Need(Marshal.ReadInt32(map,44)==2,"Index was not published");
            IntPtr ctxMain=mem.New(32),record=mem.New(32),fieldRows=mem.New(Count*8);
            Marshal.WriteInt32(record,0x464d4150);Marshal.WriteInt32(record,4,1);Marshal.WriteInt32(record,8,Count);Marshal.WriteInt32(record,12,8);
            Marshal.WriteIntPtr(record,24,fieldRows);
            for(int i=0;i<Count;i++){Marshal.WriteInt32(fieldRows,i*8,i);Marshal.WriteInt32(fieldRows,i*8+4,8+(i%2)*8);}
            long used=Marshal.ReadInt64(heap,48);
            for(int i=0;i<Count;i++) {
                Marshal.WriteIntPtr(first,-8,new IntPtr(0x10000L+i*16L));
                IntPtr row=rowQuery(first,map,ctxMain);
                Need(row==IntPtr.Add(rows,i*40)&&Marshal.ReadInt32(row,16)==i&&Marshal.ReadInt32(ctxMain)==0,"Indexed receiver identity differs");
                Need(field(first,ctxMain,record,map)==IntPtr.Add(first,8+(i%2)*8)&&Marshal.ReadInt32(ctxMain)==0,"Binary field lookup differs");
            }
            Parallel.For(0,8,worker=>{IntPtr ctx=Marshal.AllocHGlobal(32);try{for(int i=0;i<32;i++)Marshal.WriteByte(ctx,i,0);
                for(int n=0;n<16384;n++)Need(query(last,map,ctx)==descriptor&&Marshal.ReadInt32(ctx)==0,"Hot index lookup failed");
            }finally{Marshal.FreeHGlobal(ctx);}});
            Need(Marshal.ReadInt64(heap,48)==used,"Type/field lookup allocated guest memory");
            Need(cast(last,map,descriptor,ctxMain)==unchecked((ulong)last.ToInt64())&&Marshal.ReadInt32(ctxMain)==0,"Large-map cast failed");
            Marshal.WriteInt32(ctxMain,3);Marshal.WriteInt32(ctxMain,4,123);Marshal.WriteInt32(ctxMain,8,456);
            Need(rowQuery(last,map,ctxMain)==IntPtr.Zero&&field(last,ctxMain,record,map)==IntPtr.Zero&&prepare(map,ctxMain)==1
                 &&Marshal.ReadInt32(ctxMain)==3&&Marshal.ReadInt32(ctxMain,4)==123&&Marshal.ReadInt32(ctxMain,8)==456,"Pending error changed");
            Need(rowQuery(IntPtr.Zero,map,ctxMain)==IntPtr.Zero&&Marshal.ReadInt32(ctxMain)==3,"Null receiver replaced pending error");
            Marshal.WriteInt32(ctxMain,0);
            SetException set=Symbol<SetException>(module,"boom_exception_set32");MatchException match=Symbol<MatchException>(module,"boom_exception_match32");
            IntPtr handlers=mem.New(40),handlerRow=mem.New(24);
            Marshal.WriteInt32(handlers,0x45584348);Marshal.WriteInt32(handlers,4,1);Marshal.WriteInt32(handlers,8,1);
            Marshal.WriteIntPtr(handlers,16,handlerRow);Marshal.WriteIntPtr(handlers,24,map);Marshal.WriteIntPtr(handlers,32,descriptor);
            Marshal.WriteInt32(handlerRow,4,20);Marshal.WriteInt32(handlerRow,8,8);Marshal.WriteIntPtr(handlerRow,16,descriptor);
            Need(set(ctxMain,last,map,descriptor)==16&&Marshal.ReadInt32(ctxMain)==16,"ABI2 Throwable publication failed");
            Need(query(last,map,ctxMain)==descriptor&&Marshal.ReadInt32(ctxMain)==16,"Pending Throwable type was not queryable");
            Need(match(ctxMain,4,handlers)==9&&Marshal.ReadInt32(ctxMain)==16&&Marshal.ReadIntPtr(ctxMain,16)==last
                 &&Marshal.ReadInt32(ctxMain,4)==123&&Marshal.ReadInt32(ctxMain,8)==456,"ABI2 ordered catch changed Throwable/root/origin");
            GC.KeepAlive(set);GC.KeepAlive(match);Marshal.WriteIntPtr(ctxMain,16,IntPtr.Zero);
            Marshal.WriteInt32(ctxMain,0);Need(rowQuery(IntPtr.Zero,map,ctxMain)==IntPtr.Zero&&Marshal.ReadInt32(ctxMain)==4,"Null receiver accepted");
            Marshal.WriteInt32(ctxMain,0);Marshal.WriteIntPtr(last,-8,new IntPtr(0x77777777));
            Need(rowQuery(last,map,ctxMain)==IntPtr.Zero&&Marshal.ReadInt32(ctxMain)==7,"Unknown heap tag accepted");
            Marshal.WriteInt32(ctxMain,0);Marshal.WriteIntPtr(last,-8,new IntPtr(0x10000L+(Count-1)*16L));Marshal.WriteInt64(last,-16,31);
            Need(rowQuery(last,map,ctxMain)==IntPtr.Zero&&Marshal.ReadInt32(ctxMain)==7,"Wrong payload shape accepted");Marshal.WriteInt64(last,-16,32);
            Marshal.WriteInt32(ctxMain,0);Marshal.WriteInt32(record,16,1);
            Need(field(last,ctxMain,record,map)==IntPtr.Zero&&Marshal.ReadInt32(ctxMain)==7,"Reference field outside traced prefix accepted");
            Marshal.WriteInt32(ctxMain,0);Marshal.WriteInt32(map,40,Slots-2);
            Need(prepare(map,ctxMain)==1&&Marshal.ReadInt32(ctxMain)==7,"Invalid hash mask accepted");Marshal.WriteInt32(map,40,Slots-1);
            Marshal.WriteInt32(ctxMain,0);Marshal.WriteInt32(map,44,0);Marshal.WriteIntPtr(rows,40,new IntPtr(0x10000));
            Need(prepare(map,ctxMain)==1&&Marshal.ReadInt32(ctxMain)==7&&Marshal.ReadInt32(map,44)==3,"Duplicate tag index accepted");
            Marshal.WriteInt32(ctxMain,0);Need(prepare(map,ctxMain)==1&&Marshal.ReadInt32(ctxMain)==7,"Rejected index was retried");
            GC.KeepAlive(query);GC.KeepAlive(rowQuery);GC.KeepAlive(prepare);GC.KeepAlive(field);GC.KeepAlive(cast);GC.KeepAlive(alloc);
            return new long[]{Count,Capacity,Count*2L+8L+8L*16384,Slots,8};
        }} finally {if(heap!=IntPtr.Zero)destroy(heap);NativeLibrary.Free(module);GC.KeepAlive(destroy);}
    }
}
