// Development FFI. Only fixture objects/tables are written here. Registration,
// field access and Windows standard-handle calls execute the assembly kernels.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomFileBootstrapProviderProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Service(IntPtr ctx,IntPtr args,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Descriptor(IntPtr ctx,IntPtr stream,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int handle);
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static int I(JsonElement e,string key){return e.GetProperty(key).GetInt32();}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static void Reset(IntPtr ctx){for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);}
    public static long[] Run(string sourcePath,string kernel){
        using var doc=JsonDocument.Parse(File.ReadAllText(sourcePath));var source=doc.RootElement;var meta=source.GetProperty("metadata");
        var streams=meta.GetProperty("streams");var fd=meta.GetProperty("descriptor");var owned=new List<IntPtr>();IntPtr heap=IntPtr.Zero;
        IntPtr lib=NativeLibrary.Load(source.GetProperty("runtime").GetString()),image=NativeLibrary.Load(source.GetProperty("image").GetString()),dll=NativeLibrary.Load(kernel);bool success=false;
        IntPtr Memory(int bytes){var p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i++)Marshal.WriteByte(p,i,0);owned.Add(p);return p;}
        try{
            var ctx=Memory(32);var args=Memory(16);heap=Fn<Create>(lib,"boom_heap_create")(32UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"File bootstrap heap binding failed");
            var cp=NativeLibrary.GetExport(image,"boom_java_class_pool");var map=Marshal.ReadIntPtr(cp,40);var rows=Marshal.ReadIntPtr(map,16);
            IntPtr Layout(int id){for(int i=0;i<Marshal.ReadInt32(map,8);i++){var r=IntPtr.Add(rows,40*i);if(Marshal.ReadInt32(r,16)==id&&Marshal.ReadInt32(r,20)==0)return Marshal.ReadIntPtr(r);}throw new Exception("File normal source layout missing: "+id);}
            var tables=new IntPtr[2];var pools=new IntPtr[2];var objects=new IntPtr[2];var make=Fn<New>(lib,"boom_object_new");var descriptorObject=make(heap,Layout(I(fd,"class_id")),ctx);
            Need(descriptorObject!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal descriptor fixture allocation failed");
            for(int i=0;i<2;i++){
                var t=tables[i]=Memory(32);var p=pools[i]=Memory(32);var layout=Layout(I(streams[i],"class_id"));
                Marshal.WriteInt32(t,unchecked((int)0x53465442));Marshal.WriteInt32(t,4,1);Marshal.WriteIntPtr(t,8,layout);Marshal.WriteInt32(t,16,I(streams[i],"fd_offset"));Marshal.WriteInt32(t,20,8);
                Marshal.WriteInt32(p,unchecked((int)0x5346504c));Marshal.WriteInt32(p,4,1);Marshal.WriteIntPtr(p,8,t);
                objects[i]=make(heap,layout,ctx);Need(objects[i]!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal stream fixture allocation failed");Marshal.WriteIntPtr(objects[i],I(streams[i],"fd_offset"),descriptorObject);
            }
            var ft=Memory(48);var fp=Memory(32);Marshal.WriteInt32(ft,unchecked((int)0x46445442));Marshal.WriteInt32(ft,4,1);Marshal.WriteIntPtr(ft,8,Layout(I(fd,"class_id")));
            int at=16;foreach(var field in fd.GetProperty("fields").EnumerateArray()){Marshal.WriteInt32(ft,at,I(field,"offset"));Marshal.WriteInt32(ft,at+4,I(field,"width"));at+=8;}
            Marshal.WriteInt32(fp,unchecked((int)0x4644504c));Marshal.WriteInt32(fp,4,1);Marshal.WriteIntPtr(fp,8,ft);
            var pool=Memory(48);Marshal.WriteInt32(pool,unchecked((int)0x4f49464e));Marshal.WriteInt32(pool,4,1);Marshal.WriteIntPtr(pool,8,pools[0]);Marshal.WriteIntPtr(pool,16,pools[1]);Marshal.WriteIntPtr(pool,24,fp);
            var call=Fn<Service>(dll,"boom_provider_file_bootstrap_service");var get=Fn<Descriptor>(lib,"boom_stream_descriptor");int errors=0;
            void Error(Action action,int kind,string message){Reset(ctx);action();Need(Marshal.ReadInt32(ctx)==kind,message+" kind="+Marshal.ReadInt32(ctx));errors++;Reset(ctx);}
            Error(()=>call(ctx,args,pool,3),20,"Unregistered descriptor handle lookup succeeded");
            Error(()=>get(ctx,objects[0],pools[0]),20,"Unregistered stream descriptor lookup succeeded");
            for(uint op=0;op<3;op++)Need(call(ctx,args,pool,op)==0&&Marshal.ReadInt32(ctx)==0,"Normal field registration failed");
            for(int i=0;i<2;i++){Need(Marshal.ReadIntPtr(pools[i],16)==tables[i]&&get(ctx,objects[i],pools[i])==descriptorObject&&Marshal.ReadInt32(ctx)==0,"Registered normal stream fd mapping differs");}
            Need(Marshal.ReadIntPtr(fp,16)==ft,"Normal descriptor fields were not published");
            int cases=0;foreach(int number in new[]{int.MinValue,-2,-1,0,1,2,3,int.MaxValue}){
                Marshal.WriteInt64(args,number);long expected=number>=0&&number<=2?GetStdHandle(-10-number).ToInt64():-1;
                Need(call(ctx,args,pool,3)==expected&&call(ctx,args,pool,4)==0&&Marshal.ReadInt32(ctx)==0,"Windows descriptor handle/append policy differs");cases++;
            }
            Error(()=>call(ctx,args,IntPtr.Zero,0),7,"Missing file pool accepted");
            Error(()=>call(ctx,args,pool,6),7,"Unknown file operation accepted");
            Need(call(ctx,IntPtr.Zero,pool,5)==(BitConverter.IsLittleEndian?0:1)&&Marshal.ReadInt32(ctx)==0,"Native DWORD byte-order observation differs");
            Marshal.WriteInt64(pool,32,1);Error(()=>call(ctx,args,pool,0),7,"Nonzero file pool reservation accepted");Marshal.WriteInt64(pool,32,0);
            Marshal.WriteInt32(ft,20,8);Error(()=>call(ctx,args,pool,2),7,"Incorrect source int field width accepted");Marshal.WriteInt32(ft,20,4);
            Marshal.WriteIntPtr(fp,16,tables[0]);Error(()=>call(ctx,args,pool,2),7,"Conflicting descriptor registration accepted");Marshal.WriteIntPtr(fp,16,ft);
            Error(()=>call(ctx,IntPtr.Zero,pool,3),7,"Missing handle argument accepted");
            Error(()=>get(ctx,IntPtr.Zero,pools[0]),4,"Null stream did not preserve NPE");
            Marshal.WriteInt32(ctx,18);Marshal.WriteInt32(ctx,4,123);Need(call(ctx,IntPtr.Zero,IntPtr.Zero,uint.MaxValue)==0&&Marshal.ReadInt32(ctx)==18&&Marshal.ReadInt32(ctx,4)==123,"Pending error was overwritten");errors++;Reset(ctx);
            Need(call(IntPtr.Zero,args,pool,0)==0,"Null file Context was dereferenced");errors++;
            const int workers=8,iterations=1024;
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{for(int i=0;i<iterations;i++){Reset(c);int number=i%3;Marshal.WriteInt64(a,number);Need(call(c,a,pool,3)==GetStdHandle(-10-number).ToInt64()&&call(c,a,pool,4)==0&&call(c,a,pool,(uint)number)==0&&Marshal.ReadInt32(c)==0,"Concurrent normal file bootstrap failed");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            success=true;return new long[]{3,cases,errors,workers,workers*iterations*3};
        }finally{
            if(success)Need(Fn<Release>(image,"boom_release_trace_pool")()==0,"File bootstrap source retained frames");
            if(heap!=IntPtr.Zero){int freed=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(freed==1,"File bootstrap heap cleanup failed");}
            foreach(var p in owned)Marshal.FreeHGlobal(p);if(success){NativeLibrary.Free(dll);NativeLibrary.Free(image);NativeLibrary.Free(lib);}
        }
    }
}
