// Explicit FFI metadata/receiver fixtures, not original Java frame execution.
// Heap allocation, ABI3 trace handling and backtrace capture execute assembly.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomNormalThrowableKernelProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Fill(IntPtr ctx,IntPtr args,IntPtr plan);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Enter(IntPtr pool,IntPtr node,IntPtr row,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Leave(IntPtr pool,IntPtr node,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release(IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int SourceRelease();
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static int I(JsonElement e,string key){return e.GetProperty(key).GetInt32();}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string runtime,string image,string kernel,string configuration){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var meta=doc.RootElement;var receivers=meta.GetProperty("rows").EnumerateArray().ToArray();int root=I(meta,"root");
        IntPtr lib=NativeLibrary.Load(runtime),source=NativeLibrary.Load(image),dll=NativeLibrary.Load(kernel),heap=IntPtr.Zero,small=IntPtr.Zero;bool success=false;
        var owned=new List<IntPtr>();IntPtr Memory(int n){var p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);owned.Add(p);return p;}
        IntPtr trace=IntPtr.Zero;
        try{
            var ctx=Memory(32);var other=Memory(32);var args=Memory(16);heap=Fn<Create>(lib,"boom_heap_create")(64UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(source,"boom_java_string_literals_bind_heap")(heap)==1,"Normal Throwable heap binding failed");
            var cp=NativeLibrary.GetExport(source,"boom_java_class_pool");var map=Marshal.ReadIntPtr(cp,40);var maps=Marshal.ReadIntPtr(map,16);var shapes=new Dictionary<int,Tuple<IntPtr,IntPtr>>();
            for(int i=0;i<Marshal.ReadInt32(map,8);i++){var r=IntPtr.Add(maps,40*i);if(Marshal.ReadInt32(r,20)==0)shapes[Marshal.ReadInt32(r,16)]=Tuple.Create(Marshal.ReadIntPtr(r),Marshal.ReadIntPtr(r,8));}
            var rootType=shapes[root].Item2;var table=Memory(receivers.Length*48);var cell=Memory(8);Marshal.WriteIntPtr(cell,heap);
            for(int i=0;i<receivers.Length;i++){
                var r=receivers[i];var p=IntPtr.Add(table,i*48);var shape=shapes[I(r,"class_id")];Marshal.WriteIntPtr(p,shape.Item1);
                Marshal.WriteInt32(p,8,I(r,"backtrace"));Marshal.WriteInt32(p,12,I(r,"depth"));Marshal.WriteInt32(p,16,I(r,"depth_width"));Marshal.WriteInt32(p,20,I(r,"stack_trace"));Marshal.WriteIntPtr(p,32,shape.Item2);
            }
            trace=Memory(48);var row=Memory(32);Marshal.WriteInt32(trace,unchecked((int)0x5452504c));Marshal.WriteInt32(trace,4,3);Marshal.WriteInt32(trace,16,1);Marshal.WriteIntPtr(trace,24,row);
            Marshal.WriteInt32(row,123);Marshal.WriteIntPtr(row,8,rootType);Marshal.WriteInt32(row,20,root);
            var pool=Memory(64);Marshal.WriteInt32(pool,unchecked((int)0x5048544e));Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,8,receivers.Length);Marshal.WriteIntPtr(pool,16,table);Marshal.WriteIntPtr(pool,24,trace);Marshal.WriteIntPtr(pool,32,cell);Marshal.WriteIntPtr(pool,40,rootType);
            var make=Fn<New>(lib,"boom_object_new");var fill=Fn<Fill>(dll,"boom_normal_throwable_fill");var enter=Fn<Enter>(lib,"boom_trace_enter");var leave=Fn<Leave>(lib,"boom_trace_leave");
            int layouts=0;IntPtr rootObject=IntPtr.Zero;var rootFields=receivers.Single(r=>I(r,"class_id")==root);
            void CheckTrace(IntPtr obj,JsonElement fields,int count){var back=Marshal.ReadIntPtr(obj,I(fields,"backtrace"));Need(Marshal.ReadInt32(obj,I(fields,"depth"))==count&&Marshal.ReadIntPtr(obj,I(fields,"stack_trace"))==IntPtr.Zero,"Normal Throwable field publication differs");Need(back!=IntPtr.Zero&&Marshal.ReadInt64(back,-8)==267&&Marshal.ReadInt32(back,-20)==0&&Marshal.ReadInt64(back,-16)==(count+2)*8L&&Marshal.ReadInt64(back)==0x0000000142545243L&&Marshal.ReadIntPtr(back,8)==trace,"Normal Throwable primitive backtrace shape differs");}
            foreach(var r in receivers){
                var obj=make(heap,shapes[I(r,"class_id")].Item1,ctx);Need(obj!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal Throwable layout allocation failed");Marshal.WriteIntPtr(args,obj);
                Need(fill(ctx,args,pool)==obj&&Marshal.ReadInt32(ctx)==0,"Normal Throwable receiver was rejected");CheckTrace(obj,r,0);layouts++;if(I(r,"class_id")==root)rootObject=obj;
            }
            var node=Memory(48);int frameCases=0;Marshal.WriteIntPtr(args,rootObject);
            foreach(var item in new[]{Tuple.Create(32,0,1),Tuple.Create(48,0,0),Tuple.Create(36,0,1),Tuple.Create(34,0,0),Tuple.Create(1,16,0),Tuple.Create(2,16,0)}){
                Marshal.WriteInt32(row,4,item.Item1);Marshal.WriteInt32(row,16,item.Item2);Need(enter(trace,node,row,ctx)==0,"ABI3 Throwable fixture entry failed");
                Need(fill(ctx,args,pool)==rootObject&&Marshal.ReadInt32(ctx)==0,"ABI3 Throwable native/visibility fixture failed");CheckTrace(rootObject,rootFields,item.Item3);
                if(item.Item3==1){var back=Marshal.ReadIntPtr(rootObject,I(rootFields,"backtrace"));Need(unchecked((ulong)Marshal.ReadInt64(back,16))==(123UL<<32),"ABI3 native frame identity differs");}
                Need(leave(trace,node,ctx)==0,"ABI3 Throwable fixture leave failed");frameCases++;
            }
            Marshal.WriteInt32(row,4,32);Marshal.WriteInt32(row,16,0);Need(enter(trace,node,row,other)==0,"Other Context fixture entry failed");Need(fill(ctx,args,pool)==rootObject&&Marshal.ReadInt32(ctx)==0,"Context boundary capture failed");CheckTrace(rootObject,rootFields,0);Need(leave(trace,node,other)==0,"Other Context fixture leave failed");frameCases++;
            Need(enter(trace,node,row,ctx)==0,"Native PC fixture entry failed");Marshal.WriteInt32(node,24,1);Need(fill(ctx,args,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Nonzero native BCI accepted");Need(leave(trace,node,ctx)==0,"Native error fixture retained its trace frame");Reset(ctx);frameCases++;
            small=Fn<Create>(lib,"boom_heap_create")(4096);Need(small!=IntPtr.Zero,"Small Throwable heap allocation failed");var smallObject=make(small,shapes[root].Item1,ctx);Need(smallObject!=IntPtr.Zero,"Small Throwable receiver allocation failed");
            var allocate=Fn<Alloc>(lib,"boom_heap_alloc");int fillers=0;while(allocate(small,0,0,264)!=IntPtr.Zero){Need(++fillers<1000000,"Small heap did not become exhausted");}
            Marshal.WriteIntPtr(cell,small);Marshal.WriteIntPtr(args,smallObject);Need(fill(ctx,args,pool)==smallObject&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadIntPtr(smallObject,I(rootFields,"backtrace"))==IntPtr.Zero&&Marshal.ReadInt32(smallObject,I(rootFields,"depth"))==0,"Backtrace allocation OOM was not suppressed");Marshal.WriteIntPtr(cell,heap);
            const int workers=8,iterations=64;
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{Reset(c);var obj=make(heap,shapes[root].Item1,c);Need(obj!=IntPtr.Zero,"Concurrent Throwable receiver allocation failed");Marshal.WriteIntPtr(a,obj);Marshal.WriteInt64(a,8,0);for(int i=0;i<iterations;i++){Need(fill(c,a,pool)==obj&&Marshal.ReadInt32(c)==0,"Concurrent normal Throwable capture failed");CheckTrace(obj,rootFields,0);}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            success=true;return new long[]{layouts,frameCases,1,workers,workers*iterations};
        }finally{
            if(trace!=IntPtr.Zero){int released=Fn<Release>(lib,"boom_trace_release")(trace);if(success)Need(released==0,"Normal Throwable fixture retained TLS frames");}
            if(success)Need(Fn<SourceRelease>(source,"boom_release_trace_pool")()==0,"Normal Throwable source image retained frames");
            if(small!=IntPtr.Zero)Fn<Destroy>(lib,"boom_heap_destroy")(small);if(heap!=IntPtr.Zero){int freed=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(freed==1,"Normal Throwable heap cleanup failed");}
            foreach(var p in owned)Marshal.FreeHGlobal(p);if(success){NativeLibrary.Free(dll);NativeLibrary.Free(source);NativeLibrary.Free(lib);}
        }
    }
}
