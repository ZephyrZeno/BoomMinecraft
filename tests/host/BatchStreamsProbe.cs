using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Development host. Source constructor/read bodies, monitors, native setters,
// type checks, allocation and collection execute assembly. Output receivers use
// source shapes; their Java constructors and file/console I/O are not run.
public static class BoomBatchStreamsProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewArray(IntPtr heap,IntPtr counts,IntPtr type,uint dimensions,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static void Need(bool value,string text){if(!value)throw new Exception(text);}
    static void Reset(IntPtr ctx){for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);Marshal.WriteInt32(ctx,4,37);Marshal.WriteInt32(ctx,8,73);}
    static IntPtr Context(){IntPtr p=Marshal.AllocHGlobal(32);Reset(p);return p;}
    static int Call(Entry entry,IntPtr ctx,IntPtr args){ulong value=entry(ctx,args);Need(Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(ctx,12)==0,"Original input method failed");return unchecked((int)value);}
    public static long[] Run(string runtime,string dll,string directory,int systemId,int inputId,int printId,int objectId,int byteArrayId,
        string setIn,string setOut,string setErr,string constructor,string readName,string availableName,string resetName){
        IntPtr library=NativeLibrary.Load(runtime),module=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,args=IntPtr.Zero,counts=IntPtr.Zero,rootMemory=IntPtr.Zero;
        var destroy=Symbol<Destroy>(library,"boom_heap_destroy");
        try{
            module=NativeLibrary.Load(dll);ctx=Context();args=Marshal.AllocHGlobal(16);counts=Marshal.AllocHGlobal(8);
            var setters=new Entry[]{Symbol<Entry>(module,setIn),Symbol<Entry>(module,setOut),Symbol<Entry>(module,setErr)};
            IntPtr streamPool=NativeLibrary.GetExport(module,"boom_batch_system_stream_pool"),slots=Marshal.ReadIntPtr(streamPool,32);
            IntPtr[] cells={Marshal.ReadIntPtr(slots),Marshal.ReadIntPtr(slots,16),Marshal.ReadIntPtr(slots,32)};
            // Native wrappers perform original System initialization themselves.
            Marshal.WriteIntPtr(args,IntPtr.Zero);
            for(int op=0;op<3;op++){Reset(ctx);setters[op](ctx,args);Need(Marshal.ReadInt32(ctx)==0&&Marshal.ReadIntPtr(cells[op])==IntPtr.Zero,"Null setter before heap binding failed");}
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(module,"boom_class"+systemId),8)==2,"System initialization missing");
            heap=Symbol<Create>(library,"boom_heap_create")(16*1024*1024);Need(heap!=IntPtr.Zero&&Symbol<Bind>(module,"boom_java_string_literals_bind_heap")(heap)==1,"Stream heap bind failed");
            var make=Symbol<Make>(library,"boom_object_new");var allocate=Symbol<NewArray>(library,"boom_typed_multi_new");var collect=Symbol<Collect>(library,"boom_heap_collect");
            IntPtr map=NativeLibrary.GetExport(module,"boom_runtime_type_map"),types=NativeLibrary.GetExport(module,"boom_batch_type_descriptors"),sourceRows=Marshal.ReadIntPtr(map,16);
            var layouts=new Dictionary<int,IntPtr>();for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(sourceRows,i*40);if(Marshal.ReadInt32(row,20)==0)layouts.Add(Marshal.ReadInt32(row,16),Marshal.ReadIntPtr(row));}
            Reset(ctx);Marshal.WriteInt64(counts,3);IntPtr data=allocate(heap,counts,Marshal.ReadIntPtr(types,byteArrayId*8),1,ctx);
            Need(data!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Input backing byte array allocation failed");Marshal.WriteByte(data,0,7);Marshal.WriteByte(data,1,10);Marshal.WriteByte(data,2,255);
            IntPtr input=make(heap,layouts[inputId],ctx),output=make(heap,layouts[printId],ctx),error=make(heap,layouts[printId],ctx),plain=make(heap,layouts[objectId],ctx);
            Need(input!=IntPtr.Zero&&output!=IntPtr.Zero&&error!=IntPtr.Zero&&plain!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Source stream receiver allocation failed");
            Marshal.WriteIntPtr(args,input);Marshal.WriteIntPtr(args,8,data);Call(Symbol<Entry>(module,constructor),ctx,args);
            var read=Symbol<Entry>(module,readName);var available=Symbol<Entry>(module,availableName);var reset=Symbol<Entry>(module,resetName);
            Marshal.WriteIntPtr(args,input);string sequence=Call(available,ctx,args)+","+Call(read,ctx,args)+","+Call(read,ctx,args)+","+Call(read,ctx,args)+","+Call(read,ctx,args);
            Call(reset,ctx,args);sequence+=","+Call(available,ctx,args);
            Need(sequence==File.ReadAllText(Path.Combine(directory,"oracle.txt")).Trim(),"Original input constructor/read/reset differs from JVM");
            long published=0,shapeCount=0;
            foreach(string line in File.ReadLines(Path.Combine(directory,"receivers.tsv"))){string[] p=line.Split('\t');int id=int.Parse(p[0]),mask=int.Parse(p[1]);Reset(ctx);IntPtr value=make(heap,layouts[id],ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Source stream subtype shape failed");
                for(int op=0;op<3;op++)if((mask&(1<<op))!=0){Marshal.WriteIntPtr(args,value);long used=Marshal.ReadInt64(heap,48);setters[op](ctx,args);
                    Need(Marshal.ReadInt32(ctx)==0&&Marshal.ReadIntPtr(cells[op])==value&&Marshal.ReadInt64(heap,48)==used,"Setter did not publish real rooted subtype cell without allocation");published++;}
                shapeCount++;
            }
            IntPtr[] correct={input,output,error};for(int op=0;op<3;op++){Reset(ctx);Marshal.WriteIntPtr(args,correct[op]);setters[op](ctx,args);Need(Marshal.ReadIntPtr(cells[op])==correct[op]&&Marshal.ReadInt32(ctx)==0,"Final stream publication failed");}
            int failures=0;
            for(int op=0;op<3;op++){
                Reset(ctx);Marshal.WriteIntPtr(args,plain);setters[op](ctx,args);Need(Marshal.ReadInt32(ctx)==7&&Marshal.ReadIntPtr(cells[op])==correct[op],"Invalid stream type changed root");failures++;
                Reset(ctx);setters[op](ctx,IntPtr.Zero);Need(Marshal.ReadInt32(ctx)==7&&Marshal.ReadIntPtr(cells[op])==correct[op],"Invalid argv changed stream root");failures++;
                Reset(ctx);Marshal.WriteInt32(ctx,16);Marshal.WriteIntPtr(ctx,16,input);Marshal.WriteIntPtr(args,IntPtr.Zero);setters[op](ctx,args);
                Need(Marshal.ReadInt32(ctx)==16&&Marshal.ReadIntPtr(ctx,16)==input&&Marshal.ReadIntPtr(cells[op])==correct[op],"Pending exception changed stream root");failures++;
            }
            const int workers=8,rounds=1024;long warm=Marshal.ReadInt64(heap,48);
            Parallel.For(0,workers,worker=>{IntPtr context=Context(),arguments=Marshal.AllocHGlobal(8);try{for(int n=0;n<rounds;n++){
                Reset(context);int op=(worker+n)%3;Marshal.WriteIntPtr(arguments,(n&1)==0?correct[op]:IntPtr.Zero);setters[op](context,arguments);Need(Marshal.ReadInt32(context)==0,"Concurrent stream setter failed");
            }}finally{Marshal.FreeHGlobal(context);Marshal.FreeHGlobal(arguments);}});
            Need(Marshal.ReadInt64(heap,48)==warm,"Concurrent setters allocated guest objects");
            for(int op=0;op<3;op++){Reset(ctx);Marshal.WriteIntPtr(args,correct[op]);setters[op](ctx,args);}
            IntPtr roots=NativeLibrary.GetExport(module,"boom_probe_static_roots");long rootCount=Marshal.ReadInt64(NativeLibrary.GetExport(module,"boom_probe_static_root_count"));
            rootMemory=Marshal.AllocHGlobal(checked((int)(rootCount*8)));
            Action snapshot=()=>{for(int i=0;i<rootCount;i++)Marshal.WriteIntPtr(rootMemory,i*8,Marshal.ReadIntPtr(roots,i*8));};snapshot();
            // Synchronized source reads reuse one assembly monitor node. The
            // idle registry releases its strong receiver before quiescent GC.
            Need(Marshal.ReadInt64(heap,96)==0&&Marshal.ReadInt64(heap,112)==0,"Source input monitor remained active");
            long idleMonitors=0;for(IntPtr node=Marshal.ReadIntPtr(heap,120);node!=IntPtr.Zero;node=Marshal.ReadIntPtr(node,8)){
                Need(++idleMonitors<=1&&Marshal.ReadIntPtr(node)==IntPtr.Zero&&Marshal.ReadInt64(node,16)==0&&Marshal.ReadInt64(node,24)==0,"Source input idle monitor was not cleared/reused");
            }
            Need(idleMonitors==1,"Synchronized source input did not reuse its monitor");
            long beforeCollection=Marshal.ReadInt64(heap,56);Need(beforeCollection==shapeCount+5+idleMonitors,"Unexpected guest allocation during source stream calls");
            long freed=collect(heap,rootMemory,(ulong)rootCount);Need(freed==shapeCount+1+idleMonitors&&Marshal.ReadInt64(heap,56)==4,"Overwritten subtype/idle monitor collection differs: freed="+freed+", before="+beforeCollection+", after="+Marshal.ReadInt64(heap,56));
            Need(Marshal.ReadIntPtr(cells[0])==input&&Marshal.ReadIntPtr(cells[1])==output&&Marshal.ReadIntPtr(cells[2])==error,"Real stream statics changed after collection");
            Reset(ctx);Marshal.WriteIntPtr(args,Marshal.ReadIntPtr(cells[0]));Need(Call(read,ctx,args)==7&&Call(available,ctx,args)==2,"Rooted original input/backing array graph was lost");
            for(int op=0;op<3;op++){Reset(ctx);Marshal.WriteIntPtr(args,IntPtr.Zero);setters[op](ctx,args);}snapshot();
            // The post-GC source read recreated a monitor; clearing the three
            // stream cells releases the four-object graph and that idle node.
            Need(Marshal.ReadInt64(heap,56)==5&&Marshal.ReadInt64(heap,96)==0&&Marshal.ReadInt64(heap,112)==0,"Post-collection source read monitor differs");
            long final=collect(heap,rootMemory,(ulong)rootCount);Need(final==5&&Marshal.ReadInt64(heap,56)==0,"Cleared stream graph and idle monitor were not completely reclaimed");
            return new long[]{shapeCount,published,workers*rounds,workers,failures,freed-idleMonitors,final-1,idleMonitors+1};
        }finally{if(rootMemory!=IntPtr.Zero)Marshal.FreeHGlobal(rootMemory);foreach(IntPtr p in new IntPtr[]{ctx,args,counts})if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);if(heap!=IntPtr.Zero)destroy(heap);if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(library);}
    }
}
