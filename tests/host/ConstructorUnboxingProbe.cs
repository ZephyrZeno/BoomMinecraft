// Development shapes only. No claim that Java wrapper constructors executed.
// All heap validation, type matching, field reads and conversions execute ASM.
using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomConstructorUnboxingProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong n,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Unbox(IntPtr ctx,IntPtr value,uint target,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint GetCsr();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void SetCsr(uint value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr dll,string n)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,n));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string runtime,string types,string image,string configuration,string oracle){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        var cases=File.ReadAllLines(oracle).Select(l=>l.Split('\t').Select(ulong.Parse).ToArray()).ToArray();Need(cases.Length==456,"Unboxing JVM coverage changed");
        IntPtr lib=NativeLibrary.Load(runtime),data=NativeLibrary.Load(types),dll=NativeLibrary.Load(image),heap=IntPtr.Zero;
        IntPtr ctx=Marshal.AllocHGlobal(32),pool=Marshal.AllocHGlobal(48),table=Marshal.AllocHGlobal(192),cell=Marshal.AllocHGlobal(8),bad=Marshal.AllocHGlobal(48);
        var get=Fn<GetCsr>(dll,"boom_widen_probe_get_mxcsr");var set=Fn<SetCsr>(dll,"boom_widen_probe_set_mxcsr");uint original=get();bool success=false;
        try{
            Reset(ctx);for(int i=0;i<48;i++)Marshal.WriteByte(pool,i,0);heap=Fn<Create>(lib,"boom_heap_create")(64UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(data,"boom_java_string_literals_bind_heap")(heap)==1,"Unboxing heap bind failed");
            var map=Marshal.ReadIntPtr(NativeLibrary.GetExport(data,"boom_java_class_pool"),40);var mapRows=Marshal.ReadIntPtr(map,16);var allocate=Fn<New>(lib,"boom_object_new");
            IntPtr Layout(int id){for(int i=0;i<Marshal.ReadInt32(map,8);i++){var row=IntPtr.Add(mapRows,i*40);if(Marshal.ReadInt32(row,16)==id&&Marshal.ReadInt32(row,20)==0)return Marshal.ReadIntPtr(row);}throw new Exception("Original unboxing source layout missing");}
            var boxes=s.GetProperty("boxes").EnumerateArray().ToArray();Need(boxes.Length==8,"Unboxing source inventory differs");
            for(int i=0;i<8;i++){var b=boxes[i];var row=IntPtr.Add(table,i*24);Marshal.WriteInt32(row,b.GetProperty("class_id").GetInt32());Marshal.WriteInt32(row,4,i);Marshal.WriteIntPtr(row,8,Layout(b.GetProperty("class_id").GetInt32()));Marshal.WriteInt32(row,16,b.GetProperty("offset").GetInt32());Marshal.WriteInt32(row,20,b.GetProperty("width").GetInt32());}
            Marshal.WriteInt32(pool,unchecked((int)0x564e4342));Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,8,8);Marshal.WriteInt32(pool,12,24);Marshal.WriteIntPtr(cell,heap);Marshal.WriteIntPtr(pool,16,cell);Marshal.WriteIntPtr(pool,24,map);Marshal.WriteIntPtr(pool,32,table);
            var refs=new IntPtr[cases.Length];for(int i=0;i<cases.Length;i++){var b=boxes[(int)cases[i][0]];var value=allocate(heap,Layout(b.GetProperty("class_id").GetInt32()),ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal wrapper shape allocation failed");byte[] bytes=BitConverter.GetBytes(cases[i][2]);Marshal.Copy(bytes,0,IntPtr.Add(value,b.GetProperty("offset").GetInt32()),b.GetProperty("width").GetInt32());refs[i]=value;}
            var unbox=Fn<Unbox>(dll,"boom_constructor_unbox");long checks=0;
            foreach(uint csr in new uint[]{0x1f80,0x3f80,0x5f80,0x7f80,0xffc0})for(int i=0;i<cases.Length;i++){Reset(ctx);set(csr);ulong actual=unbox(ctx,refs[i],(uint)cases[i][1],pool);uint after=get();Need(actual==cases[i][4]&&Marshal.ReadInt32(ctx)==(int)cases[i][3]&&after==csr,"Normal heap unboxing differs from JVM: "+i);checks++;}
            set(original);Reset(ctx);int errors=0;
            foreach(var value in new[]{IntPtr.Zero,allocate(heap,Layout(s.GetProperty("object_class").GetInt32()),ctx),Fn<Alloc>(lib,"boom_heap_alloc")(heap,1,0,264)}){Need(unbox(ctx,value,4,pool)==0&&Marshal.ReadInt32(ctx)==18,"Non-wrapper primitive argument accepted");errors++;Reset(ctx);}
            foreach(var value in new[]{new IntPtr(1),IntPtr.Add(refs[0],1)}){Need(unbox(ctx,value,0,pool)==0&&Marshal.ReadInt32(ctx)==7,"Foreign or interior wrapper accepted");errors++;Reset(ctx);}
            byte[] bytesPool=new byte[48];Marshal.Copy(pool,bytesPool,0,48);foreach(int offset in new[]{0,4,8,12,16,24,32,40}){Marshal.Copy(bytesPool,0,bad,48);if(offset>=16&&offset<40)Marshal.WriteIntPtr(bad,offset,IntPtr.Zero);else Marshal.WriteInt32(bad,offset,123);Need(unbox(ctx,refs[0],0,bad)==0&&Marshal.ReadInt32(ctx)==7,"Malformed unboxing pool accepted: "+offset);errors++;Reset(ctx);}
            foreach(int offset in new[]{0,4,16,20}){int prior=Marshal.ReadInt32(table,offset);Marshal.WriteInt32(table,offset,int.MaxValue);Need(unbox(ctx,refs[0],0,pool)==0&&Marshal.ReadInt32(ctx)==7,"Malformed wrapper field metadata accepted: "+offset);Marshal.WriteInt32(table,offset,prior);errors++;Reset(ctx);}
            Need(unbox(ctx,refs[0],8,pool)==0&&Marshal.ReadInt32(ctx)==7,"Invalid unbox target accepted");errors++;Reset(ctx);Need(unbox(IntPtr.Zero,refs[0],0,pool)==0,"Null unbox context accepted");errors++;
            Marshal.WriteInt32(ctx,66);Need(unbox(ctx,new IntPtr(1),8,IntPtr.Zero)==0&&Marshal.ReadInt32(ctx)==66,"Unboxing overwrote pending error");errors++;Reset(ctx);
            const int workers=8,iterations=4096;long allocations=Marshal.ReadInt64(heap,48);
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);uint before=get();try{set(0xffc0);for(int i=0;i<iterations;i++){Reset(c);int at=(w+i)%cases.Length;var r=cases[at];Need(unbox(c,refs[at],(uint)r[1],pool)==r[4]&&Marshal.ReadInt32(c)==(int)r[3]&&get()==0xffc0,"Concurrent source wrapper unboxing differs");}}finally{set(before);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt64(heap,48)==allocations,"Warm unboxing allocated guest objects");success=true;return new long[]{cases.Length,checks,errors,workers,workers*iterations};
        }finally{set(original);if(heap!=IntPtr.Zero){int freed=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(freed==1,"Unboxing heap cleanup failed");}Fn<Release>(data,"boom_release_trace_pool")();foreach(var p in new[]{ctx,pool,table,cell,bad})Marshal.FreeHGlobal(p);NativeLibrary.Free(dll);NativeLibrary.Free(data);NativeLibrary.Free(lib);}
    }
}
