using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Development host only. Native allocation, indexing, field resolution, casts,
// and explicit collection use assembly. Java constructors are not invoked here.
public static class BoomBatchMetadataProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Array(IntPtr heap,int count,uint kind,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Multi(IntPtr heap,IntPtr counts,IntPtr type,uint dimensions,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Query(IntPtr value,IntPtr map,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Cast(IntPtr value,IntPtr map,IntPtr target,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(IntPtr value,IntPtr ctx,IntPtr record,IntPtr map);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Thunk(IntPtr value,IntPtr ctx);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static IntPtr Context(){IntPtr p=Marshal.AllocHGlobal(32);for(int i=0;i<32;i++)Marshal.WriteByte(p,i,0);return p;}
    public static long[] Run(string runtime,string generated,string directory,int capacity) {
        IntPtr native=NativeLibrary.Load(runtime),module=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,counts=IntPtr.Zero,roots=IntPtr.Zero;
        Destroy destroy=Symbol<Destroy>(native,"boom_heap_destroy");
        try{
            module=NativeLibrary.Load(generated);
            IntPtr map=NativeLibrary.GetExport(module,"boom_runtime_type_map"),types=NativeLibrary.GetExport(module,"boom_batch_type_descriptors"),fields=NativeLibrary.GetExport(module,"boom_batch_field_records");
            Need(Marshal.ReadInt32(map,4)==2&&Marshal.ReadInt32(map,12)==capacity,"Generated runtime map ABI differs");
            Make make=Symbol<Make>(native,"boom_object_new");Array array=Symbol<Array>(native,"boom_array_new");Multi multi=Symbol<Multi>(native,"boom_typed_multi_new");
            Query rowQuery=Symbol<Query>(native,"boom_runtime_row"),query=Symbol<Query>(native,"boom_runtime_type");Cast cast=Symbol<Cast>(native,"boom_runtime_cast");
            Field field=Symbol<Field>(native,"boom_field_address");Collect collect=Symbol<Collect>(native,"boom_heap_collect");
            var records=new List<long[]>();ulong required=1024*1024;
            foreach(string line in File.ReadLines(Path.Combine(directory,"runtime-objects.tsv"))) {
                string[] p=line.Split('\t');long[] r=new long[p.Length];for(int i=0;i<r.Length;i++)r[i]=long.Parse(p[i]);records.Add(r);
                long payload=r[1]==0?r[2]:r[1]==1?2L<<(int)r[4]:16;
                required+=(ulong)((payload+47)&~15L);
            }
            Need(records.Count==Marshal.ReadInt32(map,8),"Runtime row fixture differs");
            ulong reservation=(((required*5+3)/4)+128+4095)&~4095UL;
            heap=Symbol<Create>(native,"boom_heap_create")(reservation);Need(heap!=IntPtr.Zero,"Metadata heap creation failed");
            Need(unchecked((ulong)Marshal.ReadInt64(heap,16))>=required,"Metadata object arena is too small");
            ctx=Context();counts=Marshal.AllocHGlobal(8);Marshal.WriteInt64(counts,2);
            roots=Marshal.AllocHGlobal(records.Count*8);IntPtr[] objects=new IntPtr[capacity];
            IntPtr sourceRows=Marshal.ReadIntPtr(map,16);
            for(int index=0;index<records.Count;index++) {
                long[] r=records[index];int id=(int)r[0],kind=(int)r[1];IntPtr desc=Marshal.ReadIntPtr(types,id*8);
                Need(desc!=IntPtr.Zero,"Missing source type descriptor");
                IntPtr row=IntPtr.Add(sourceRows,index*40);Need(Marshal.ReadInt32(row,16)==id,"Runtime source row identity differs");
                IntPtr value=kind==0?make(heap,Marshal.ReadIntPtr(row),ctx):kind==1?array(heap,2,(uint)(Marshal.ReadInt64(row)-256),ctx):multi(heap,counts,desc,1,ctx);
                Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Source layout allocation failed at "+id);
                objects[id]=value;Marshal.WriteIntPtr(roots,index*8,value);
                Need(rowQuery(value,map,ctx)==row&&query(value,map,ctx)==desc&&Marshal.ReadInt32(ctx)==0,"Actual source type lookup differs at "+id);
                Need(cast(value,map,desc,ctx)==unchecked((ulong)value.ToInt64())&&Marshal.ReadInt32(ctx)==0,"Actual source identity cast failed");
            }
            long allocated=Marshal.ReadInt64(heap,48),offsets=0;
            foreach(string line in File.ReadLines(Path.Combine(directory,"runtime-fields.tsv"))) {
                string[] p=line.Split('\t');int id=int.Parse(p[0]),receiver=int.Parse(p[1]),offset=int.Parse(p[2]),bytes=int.Parse(p[3]);
                IntPtr record=Marshal.ReadIntPtr(fields,id*8),value=objects[receiver];
                Need(record!=IntPtr.Zero&&value!=IntPtr.Zero,"Missing source field receiver/record");
                IntPtr address=field(value,ctx,record,map);
                Need(address==IntPtr.Add(value,offset)&&Marshal.ReadInt32(ctx)==0,"Inherited source field address differs: "+id+"/"+receiver);
                for(int i=0;i<bytes;i++)Need(Marshal.ReadByte(address,i)==0,"New source field was not zero initialized");
                offsets++;
            }
            long thunkCalls=0;
            foreach(string line in File.ReadLines(Path.Combine(directory,"runtime-thunks.tsv"))) {
                string[] p=line.Split('\t');int id=int.Parse(p[0]),receiver=int.Parse(p[1]),offset=int.Parse(p[2]);
                Thunk thunk=Symbol<Thunk>(module,"boom_field_map"+id);
                Need(thunk(objects[receiver],ctx)==IntPtr.Add(objects[receiver],offset)&&Marshal.ReadInt32(ctx)==0,"Generated field thunk ABI differs");
                thunkCalls++;GC.KeepAlive(thunk);
            }
            Parallel.For(0,8,worker=>{IntPtr context=Context();try{
                for(int i=worker;i<records.Count;i+=8){int id=(int)records[i][0];Need(query(objects[id],map,context)==Marshal.ReadIntPtr(types,id*8)&&Marshal.ReadInt32(context)==0,"Parallel source type lookup differs");}
            }finally{Marshal.FreeHGlobal(context);}});
            Need(Marshal.ReadInt64(heap,48)==allocated,"Source metadata queries allocated guest memory");
            Need(collect(heap,roots,(ulong)records.Count)==0,"Source object roots were lost");
            Need(collect(heap,IntPtr.Zero,0)==records.Count,"Unrooted source objects were not reclaimed");
            GC.KeepAlive(make);GC.KeepAlive(array);GC.KeepAlive(multi);GC.KeepAlive(rowQuery);GC.KeepAlive(query);GC.KeepAlive(cast);GC.KeepAlive(field);GC.KeepAlive(collect);
            return new long[]{records.Count,offsets,thunkCalls,allocated,8};
        }finally{if(roots!=IntPtr.Zero)Marshal.FreeHGlobal(roots);if(counts!=IntPtr.Zero)Marshal.FreeHGlobal(counts);if(ctx!=IntPtr.Zero)Marshal.FreeHGlobal(ctx);if(heap!=IntPtr.Zero)destroy(heap);if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(native);GC.KeepAlive(destroy);}
    }
}
