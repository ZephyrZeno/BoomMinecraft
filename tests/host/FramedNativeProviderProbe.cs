// Development FFI only. Framed native entries and original Java callbacks are ASM.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomFramedNativeProviderProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong n,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int IdentityBind(IntPtr pool,uint id,IntPtr value,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr ctx,IntPtr pool,uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr lib,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static int I(JsonElement e,string key){return e.GetProperty(key).GetInt32();}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);}
    public static long[] Run(string runtime,string image,string config){
        using var doc=JsonDocument.Parse(File.ReadAllText(config));var s=doc.RootElement;
        IntPtr lib=NativeLibrary.Load(runtime),dll=NativeLibrary.Load(image),heap=IntPtr.Zero;var owned=new List<IntPtr>();bool success=false;
        IntPtr Memory(int n){var p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);owned.Add(p);return p;}
        try{
            var ctx=Memory(32);var args=Memory(16);heap=Fn<Create>(lib,"boom_heap_create")(256UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Flags heap bind failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");foreach(var id in s.GetProperty("source_class_roots").EnumerateArray().Where(id=>id.GetInt32()!=I(s,"deferred_method_class")))Need(ensure(NativeLibrary.GetExport(dll,"boom_class"+id.GetInt32()),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original flags prerequisite init failed: "+Marshal.ReadInt32(ctx));
            var cp=NativeLibrary.GetExport(dll,"boom_java_class_pool");var create=Fn<New>(lib,"boom_object_new");var alloc=Fn<Alloc>(lib,"boom_heap_alloc");
            IntPtr Layout(int id){IntPtr map=Marshal.ReadIntPtr(cp,40),table=Marshal.ReadIntPtr(map,16);for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(table,40*i);if(Marshal.ReadInt32(row,16)==id&&Marshal.ReadInt32(row,20)==0)return Marshal.ReadIntPtr(row);}throw new Exception("Fixture source layout missing");}
            var loaders=new Dictionary<int,IntPtr>{{0,IntPtr.Zero}};
            foreach(var f in s.GetProperty("fixture_loaders").EnumerateArray()){var value=create(heap,Layout(I(f,"type_id")),ctx);Need(value!=IntPtr.Zero&&Fn<IdentityBind>(lib,"boom_java_class_bind_loader")(cp,(uint)I(f,"id"),value,ctx)==1&&Marshal.ReadInt32(ctx)==0,"Flags loader fixture failed");loaders[I(f,"id")]=value;}
            foreach(var f in s.GetProperty("fixture_modules").EnumerateArray()){
                IntPtr value=create(heap,Layout(I(f,"module_type")),ctx);Need(value!=IntPtr.Zero,"Flags module fixture allocation failed");Marshal.WriteIntPtr(value,I(f,"loader_offset"),loaders[I(f,"loader")]);
                var name=f.GetProperty("name");if(name.ValueKind!=JsonValueKind.Null){byte[] bytes=Encoding.Unicode.GetBytes(name.GetString());IntPtr text=create(heap,Layout(I(s,"string_type")),ctx),data=alloc(heap,(ulong)bytes.Length,0,264);Need(text!=IntPtr.Zero&&data!=IntPtr.Zero,"Flags module name fixture failed");Marshal.Copy(bytes,0,data,bytes.Length);Marshal.WriteIntPtr(text,I(s,"string_value_offset"),data);Marshal.WriteByte(text,I(s,"string_coder_offset"),1);Marshal.WriteIntPtr(value,I(f,"name_offset"),text);}
                Need(Fn<IdentityBind>(lib,"boom_java_class_bind_module")(cp,(uint)I(f,"id"),value,ctx)==1&&Marshal.ReadInt32(ctx)==0,"Flags module fixture bind failed");
            }
            var mirror=Fn<Mirror>(lib,"boom_java_class_load");
            var accessible=NativeLibrary.GetExport(dll,"boom_class"+I(s,"cold_accessible_class"));
            var constructor=NativeLibrary.GetExport(dll,"boom_class"+I(s,"cold_constructor_class"));
            var methodClass=NativeLibrary.GetExport(dll,"boom_class"+I(s,"deferred_method_class"));
            Need(Marshal.ReadInt32(accessible,8)==0&&Marshal.ReadInt32(constructor,8)==0&&Marshal.ReadInt32(methodClass,8)==0,"Original reflection framework was not cold before native upcall");
            var objectCase=s.GetProperty("cases").EnumerateArray().First(item=>item.GetProperty("name").GetString()=="java/lang/Object");
            var objectMirror=mirror(ctx,cp,(uint)I(objectCase,"type_id"));Need(objectMirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Framed Object mirror failed");
            Marshal.WriteIntPtr(args,objectMirror);Marshal.WriteInt64(args,8,0);
            var enumeration=Fn<Entry>(dll,s.GetProperty("native_constructor_symbol").GetString());
            var array=new IntPtr(unchecked((long)enumeration(ctx,args)));var constructorPool=NativeLibrary.GetExport(dll,"boom_provider_constructor_pool");
            Need(array!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(ctx,12)==0,"Framed constructor enumeration or native frame cleanup failed");
            Need(Marshal.ReadIntPtr(array,-8)==Marshal.ReadIntPtr(constructorPool,56)&&Marshal.ReadInt32(array,-20)==1&&Marshal.ReadInt64(array,-16)==8,"Framed Object constructor array differs from original metadata");
            var ctor=Marshal.ReadIntPtr(array);Need(ctor!=IntPtr.Zero&&Marshal.ReadIntPtr(ctor,-8)==Marshal.ReadIntPtr(constructorPool,48)&&Marshal.ReadIntPtr(ctor,I(s,"constructor_clazz_offset"))==objectMirror,"Framed source Constructor object differs");
            Need(Marshal.ReadInt32(accessible,8)==2&&Marshal.ReadInt32(constructor,8)==2&&Marshal.ReadInt32(methodClass,8)==0,"Native upcall did not execute original reflection initialization in order");
            Need(ensure(methodClass,ctx)==0&&Marshal.ReadInt32(ctx)==0,"Deferred original Method initialization failed");
            var raw=Fn<Entry>(dll,s.GetProperty("native_symbols").GetProperty("0").GetString());var modifiers=Fn<Entry>(dll,s.GetProperty("native_symbols").GetProperty("1").GetString());
            var refs=new List<IntPtr>();var expected=new List<(ulong raw,ulong modifiers)>();int distinct=0,arrays=0;
            foreach(var c in s.GetProperty("cases").EnumerateArray()){
                IntPtr target=mirror(ctx,cp,(uint)I(c,"type_id"));Need(target!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Flags target mirror failed: "+c.GetProperty("name").GetString());Marshal.WriteIntPtr(args,target);
                ulong a=raw(ctx,args),b=modifiers(ctx,args);Need(a==(ulong)I(c,"raw_flags")&&b==(ulong)I(c,"modifiers")&&Marshal.ReadInt32(ctx)==0,"Original raw/modifier native mismatch: "+c.GetProperty("name").GetString());
                refs.Add(target);expected.Add((a,b));if(a!=b)distinct++;if(c.GetProperty("name").GetString().StartsWith("[")){Need(a==0,"Array raw flags were replaced by reflection modifiers");arrays++;}
            }
            Need(distinct>8&&arrays>8,"Flags fixture did not distinguish class/array contracts");
            var service=Fn<Service>(dll,"boom_provider_class_flags_service");var profile=NativeLibrary.GetExport(dll,"boom_provider_class_flags_pool");var copy=Memory(32);byte[] bytesProfile=new byte[32];Marshal.Copy(profile,bytesProfile,0,32);int errors=0;
            foreach(int offset in new[]{0,4,8,12,16,24}){Marshal.Copy(bytesProfile,0,copy,32);if(offset>=16)Marshal.WriteIntPtr(copy,offset,IntPtr.Zero);else Marshal.WriteInt32(copy,offset,123);Need(service(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==7,"Invalid class flags pool accepted");errors++;Reset(ctx);}
            Marshal.WriteIntPtr(args,IntPtr.Zero);Need(raw(ctx,args)==0&&Marshal.ReadInt32(ctx)==4,"Null raw flags Class accepted");errors++;Reset(ctx);Need(modifiers(ctx,args)==0&&Marshal.ReadInt32(ctx)==4,"Null modifier receiver accepted");errors++;Reset(ctx);
            foreach(var invalid in new[]{new IntPtr(1),IntPtr.Add(refs[0],1)}){Marshal.WriteIntPtr(args,invalid);Need(service(ctx,args,profile,0)==0&&Marshal.ReadInt32(ctx)==7,"Foreign class flags reference accepted");errors++;Reset(ctx);}
            Need(service(ctx,IntPtr.Zero,profile,0)==0&&Marshal.ReadInt32(ctx)==7,"Null flags argv accepted");errors++;Reset(ctx);Marshal.WriteIntPtr(args,refs[0]);Need(service(ctx,args,profile,2)==0&&Marshal.ReadInt32(ctx)==7,"Unknown flags operation accepted");errors++;Reset(ctx);
            Marshal.WriteInt32(ctx,66);Need(service(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==66,"Flags overwrote pending error");errors++;Reset(ctx);
            const int workers=8,iterations=2048;long allocations=Marshal.ReadInt64(heap,48);
            Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(8);try{Reset(c);for(int i=0;i<iterations;i++){int at=(w+i)%refs.Count;Marshal.WriteIntPtr(a,refs[at]);Need(raw(c,a)==expected[at].raw&&modifiers(c,a)==expected[at].modifiers&&Marshal.ReadInt32(c)==0,"Concurrent class flags changed");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt64(heap,48)==allocations,"Warm flags queries allocated guest objects");Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Flags test reached an unsupported source dependency");success=true;
            return new long[]{refs.Count,distinct,arrays,errors,workers,workers*iterations*2,1,1};
        }finally{int release=Fn<Release>(dll,"boom_release_trace_pool")();if(success)Need(release==0,"Flags retained source frames");if(heap!=IntPtr.Zero){int freed=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(freed==1,"Flags heap cleanup failed");}foreach(var p in owned)Marshal.FreeHGlobal(p);if(success){NativeLibrary.Free(dll);NativeLibrary.Free(lib);}}
    }
}
