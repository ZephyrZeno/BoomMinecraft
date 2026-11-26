// Development FFI assertions only. Guest logic, allocation and reflection are ASM.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomNormalConstructorProviderProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int BindModule(IntPtr pool,uint id,IntPtr module,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassLoad(IntPtr ctx,IntPtr pool,uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint ClassId(IntPtr ctx,IntPtr pool,IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr lib,string name) where T:Delegate {return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);}
    static int I(JsonElement e,string k){return e.GetProperty(k).GetInt32();}
    static IntPtr Ptr(ulong v){return new IntPtr(unchecked((long)v));}
    static string Context(IntPtr c){return " kind="+Marshal.ReadInt32(c)+" method="+Marshal.ReadInt32(c,8)+" pc="+Marshal.ReadInt32(c,4);}
    public static long[] Run(string runtime,string image,string sourcePath){
        using var document=JsonDocument.Parse(File.ReadAllText(sourcePath));var source=document.RootElement;
        IntPtr lib=NativeLibrary.Load(runtime),dll=NativeLibrary.Load(image),heap=IntPtr.Zero;
        var allocated=new List<IntPtr>();bool success=false;
        IntPtr Memory(int n){var p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);allocated.Add(p);return p;}
        try {
            IntPtr ctx=Memory(32),args=Memory(16);heap=Fn<Create>(lib,"boom_heap_create")(256UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Constructor heap binding failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");
            foreach(string key in new[]{"class_id","system_id"})Need(ensure(NativeLibrary.GetExport(dll,"boom_class"+I(source,key)),ctx)==0,"Original declaring class initializer failed"+Context(ctx));
            var load=Fn<ClassLoad>(lib,"boom_java_class_load");var id=Fn<ClassId>(lib,"boom_java_class_typeid");
            IntPtr classPool=NativeLibrary.GetExport(dll,"boom_java_class_pool");
            var native=Fn<Entry>(dll,source.GetProperty("native_symbol").GetString());
            var service=Fn<Service>(dll,"boom_provider_constructor_service");var profile=NativeLibrary.GetExport(dll,"boom_provider_constructor_pool");
            // Explicit development fixtures for named modules whose actual VM
            // bootstrap remains unfinished. No Module constructor/clinit claim.
            var create=Fn<New>(lib,"boom_object_new");var alloc=Fn<Alloc>(lib,"boom_heap_alloc");
            IntPtr LayoutFor(int type){IntPtr map=Marshal.ReadIntPtr(classPool,40),table=Marshal.ReadIntPtr(map,16);for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(table,40*i);if(Marshal.ReadInt32(row,16)==type&&Marshal.ReadInt32(row,20)==0)return Marshal.ReadIntPtr(row);}throw new Exception("Source fixture layout missing: "+type);}
            var fixtureLoaders=new Dictionary<int,IntPtr>();
            foreach(var fixture in source.GetProperty("fixture_loaders").EnumerateArray()){
                IntPtr loader=create(heap,LayoutFor(I(fixture,"type_id")),ctx);Need(loader!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Loader fixture allocation failed");
                Need(Fn<BindModule>(lib,"boom_java_class_bind_loader")(classPool,(uint)I(fixture,"loader_id"),loader,ctx)==1&&Marshal.ReadInt32(ctx)==0,"Loader fixture bind failed");fixtureLoaders[I(fixture,"loader_id")]=loader;
            }
            foreach(var fixture in source.GetProperty("fixture_modules").EnumerateArray()){
                IntPtr map=Marshal.ReadIntPtr(classPool,40),table=Marshal.ReadIntPtr(map,16),moduleLayout=IntPtr.Zero;
                for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(table,40*i);if(Marshal.ReadInt32(row,16)==I(fixture,"module_type")&&Marshal.ReadInt32(row,20)==0){moduleLayout=Marshal.ReadIntPtr(row);break;}}
                Need(moduleLayout!=IntPtr.Zero,"Source Module fixture layout missing");IntPtr module=create(heap,moduleLayout,ctx);
                Need(module!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Module fixture allocation failed");
                if(fixture.GetProperty("name").ValueKind!=JsonValueKind.Null){
                    IntPtr name=create(heap,Marshal.ReadIntPtr(profile,72),ctx);byte[] text=Encoding.Unicode.GetBytes(fixture.GetProperty("name").GetString());
                    IntPtr bytes=alloc(heap,(ulong)text.Length,0,264);Need(name!=IntPtr.Zero&&bytes!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Module fixture name allocation failed");
                    Marshal.Copy(text,0,bytes,text.Length);Marshal.WriteIntPtr(name,I(source,"string_value_offset"),bytes);Marshal.WriteByte(name,I(source,"string_coder_offset"),1);Marshal.WriteIntPtr(module,I(fixture,"name_offset"),name);
                }
                if(fixture.TryGetProperty("loader_id",out var fixtureLoader))Marshal.WriteIntPtr(module,I(fixture,"loader_offset"),fixtureLoaders[fixtureLoader.GetInt32()]);
                Need(Fn<BindModule>(lib,"boom_java_class_bind_module")(classPool,(uint)I(fixture,"id"),module,ctx)==1&&Marshal.ReadInt32(ctx)==0,"Module fixture bind failed");
            }
            var getters=new Dictionary<string,Entry>();foreach(var p in source.GetProperty("getters").EnumerateObject())getters[p.Name]=Fn<Entry>(dll,p.Value.GetString());
            var layout=source.GetProperty("constructor_layout");
            int Offset(string name){return layout.GetProperty("fields").EnumerateArray().Single(f=>f.GetProperty("member").GetProperty("name").GetString()==name).GetProperty("offset").GetInt32();}
            var cases=source.GetProperty("cases").EnumerateArray().ToArray();var mirrors=new List<IntPtr>();
            int records=0,signatures=0,annotations=0,parameterAnnotations=0,coldPreserved=0;
            IntPtr ctorTag=Marshal.ReadIntPtr(profile,56),classTag=Marshal.ReadIntPtr(profile,64);
            IntPtr constructorLayout=Marshal.ReadIntPtr(profile,48),stringLayout=Marshal.ReadIntPtr(profile,72);
            int ArrayLength(IntPtr array,IntPtr tag){Need(array!=IntPtr.Zero&&Marshal.ReadIntPtr(array,-8)==tag,"Reflection result has wrong array type");int n=Marshal.ReadInt32(array,-20);Need(n>=0&&Marshal.ReadInt64(array,-16)==n*8L,"Reflection result has wrong reference prefix");return n;}
            void Types(IntPtr array,JsonElement expected){int n=ArrayLength(array,classTag);Need(n==expected.GetArrayLength(),"Reflection type count differs");for(int i=0;i<n;i++)Need(id(ctx,classPool,Marshal.ReadIntPtr(array,i*8))==expected[i].GetUInt32(),"Reflection parameter/exception type differs"+Context(ctx));}
            void Bytes(IntPtr array,string hex){
                if(hex.Length==0){Need(array==IntPtr.Zero,"Absent reflection annotation became non-null");return;}
                byte[] expected=Convert.FromHexString(hex);Need(array!=IntPtr.Zero&&Marshal.ReadInt64(array,-8)==264&&Marshal.ReadInt64(array,-16)==expected.Length&&Marshal.ReadInt32(array,-20)==0,"Reflection annotation byte array shape differs");
                byte[] actual=new byte[expected.Length];Marshal.Copy(array,actual,0,actual.Length);Need(actual.SequenceEqual(expected),"Original annotation bytes changed");
            }
            foreach(var test in cases){
                int type=I(test,"type_id");IntPtr mirror=load(ctx,classPool,(uint)type);Need(mirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Target Class mirror failed for "+test.GetProperty("name").GetString()+" id="+type+Context(ctx));mirrors.Add(mirror);
                IntPtr state=IntPtr.Zero;int before=-1;if(test.GetProperty("source_class").GetBoolean()){state=NativeLibrary.GetExport(dll,"boom_class"+type);before=Marshal.ReadInt32(state,8);}
                for(int only=0;only<=1;only++){
                    var expected=test.GetProperty("constructors").EnumerateArray().Where(r=>only==0||(I(r,"modifiers")&1)!=0).ToArray();
                    Marshal.WriteIntPtr(args,mirror);Marshal.WriteInt64(args,8,only);IntPtr result=Ptr(native(ctx,args));
                    Need(Marshal.ReadInt32(ctx)==0,"Source constructor enumeration failed"+Context(ctx));Need(ArrayLength(result,ctorTag)==expected.Length,"Declared/public constructor count differs");
                    if(expected.Length>0)Need(Marshal.ReadInt32(Marshal.ReadIntPtr(profile,80),8)==2,"Enumeration did not initialize the original Constructor class");
                    var bySlot=expected.ToDictionary(r=>I(r,"slot"));
                    for(int i=0;i<expected.Length;i++){
                        IntPtr obj=Marshal.ReadIntPtr(result,i*8);Need(obj!=IntPtr.Zero&&Marshal.ReadIntPtr(obj,-8)==constructorLayout,"Constructor object is not the original source layout");
                        int slot=Marshal.ReadInt32(obj,Offset("slot"));Need(bySlot.TryGetValue(slot,out var row),"Constructor slot is not original");records++;
                        Need(Marshal.ReadIntPtr(obj,Offset("clazz"))==mirror&&Marshal.ReadByte(obj,Offset("override"))==0&&Marshal.ReadIntPtr(obj,Offset("root"))==IntPtr.Zero,"Constructor declaring class/access state differs");
                        Marshal.WriteIntPtr(args,obj);Need(Ptr(getters["getDeclaringClass"](ctx,args))==mirror,"Original declaring-class getter differs");
                        Need(unchecked((int)getters["getModifiers"](ctx,args))==I(row,"modifiers")&&unchecked((int)getters["getParameterCount"](ctx,args))==row.GetProperty("parameters").GetArrayLength(),"Original Constructor scalar getters differ");
                        Need(getters["isVarArgs"](ctx,args)==((I(row,"modifiers")&0x80)!=0?1UL:0UL)&&getters["isSynthetic"](ctx,args)==((I(row,"modifiers")&0x1000)!=0?1UL:0UL),"Original Constructor flag getters differ");
                        IntPtr params_=Ptr(getters["getParameterTypes"](ctx,args)),exceptions_=Ptr(getters["getExceptionTypes"](ctx,args));Need(Marshal.ReadInt32(ctx)==0,"Original Constructor array getter failed"+Context(ctx));
                        Types(params_,row.GetProperty("parameters"));Types(exceptions_,row.GetProperty("exceptions"));Need(params_!=Marshal.ReadIntPtr(obj,Offset("parameterTypes"))&&exceptions_!=Marshal.ReadIntPtr(obj,Offset("exceptionTypes")),"Original getter did not make a defensive copy");
                        string ann=row.GetProperty("annotations").GetString(),par=row.GetProperty("parameter_annotations").GetString();Bytes(Marshal.ReadIntPtr(obj,Offset("annotations")),ann);Bytes(Marshal.ReadIntPtr(obj,Offset("parameterAnnotations")),par);if(ann.Length>0)annotations++;if(par.Length>0)parameterAnnotations++;
                        IntPtr signature=Marshal.ReadIntPtr(obj,Offset("signature"));var sig=row.GetProperty("signature");if(sig.ValueKind==JsonValueKind.Null)Need(signature==IntPtr.Zero,"Absent generic signature became non-null");
                        else {signatures++;Need(signature!=IntPtr.Zero&&Marshal.ReadIntPtr(signature,-8)==stringLayout,"Signature is not a source String");IntPtr bytes=Marshal.ReadIntPtr(signature,I(source,"string_value_offset"));Need(Marshal.ReadByte(signature,I(source,"string_coder_offset"))==1,"Signature UTF16 coder differs");int size=checked((int)Marshal.ReadInt64(bytes,-16));byte[] b=new byte[size];Marshal.Copy(bytes,b,0,size);Need(Encoding.Unicode.GetString(b)==sig.GetString(),"Original generic signature changed");}
                    }
                }
                if(state!=IntPtr.Zero&&before==0){Need(Marshal.ReadInt32(state,8)==0,"Reflection initialized its target class");coldPreserved++;}
            }
            int errors=0;Reset(ctx);Marshal.WriteIntPtr(args,IntPtr.Zero);Marshal.WriteInt64(args,8,0);Need(native(ctx,args)==0&&Marshal.ReadInt32(ctx)==4,"Reflection null target did not throw NPE");errors++;Reset(ctx);
            foreach(var invalid in new[]{new IntPtr(1),IntPtr.Add(mirrors[0],1)}){Marshal.WriteIntPtr(args,invalid);Need(service(ctx,args,profile,0)==0&&Marshal.ReadInt32(ctx)==7,"Foreign Class accepted");errors++;Reset(ctx);}
            Marshal.WriteIntPtr(args,mirrors[0]);Need(service(ctx,args,profile,1)==0&&Marshal.ReadInt32(ctx)==7,"Unknown reflection operation accepted");errors++;Reset(ctx);
            IntPtr bad=Memory(160);byte[] bytesProfile=new byte[160];Marshal.Copy(profile,bytesProfile,0,160);
            foreach(int offset in new[]{0,4,8,104,112,116,120,124,128,132,136,144,152}){Marshal.Copy(bytesProfile,0,bad,160);Marshal.WriteInt32(bad,offset,123);Need(service(ctx,args,bad,0)==0&&Marshal.ReadInt32(ctx)==7,"Malformed reflection pool accepted: "+offset);errors++;Reset(ctx);}
            Marshal.WriteInt32(ctx,66);Need(service(ctx,args,profile,0)==0&&Marshal.ReadInt32(ctx)==66,"Reflection overwrote pending error");errors++;Reset(ctx);
            const int workers=8,iterations=64;
            Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(16);try{Reset(c);for(int i=0;i<iterations;i++){int at=(w+i)%cases.Length;Marshal.WriteIntPtr(a,mirrors[at]);Marshal.WriteInt64(a,8,0);IntPtr result=Ptr(native(c,a));Need(Marshal.ReadInt32(c)==0&&ArrayLength(result,ctorTag)==cases[at].GetProperty("constructors").GetArrayLength(),"Concurrent reflection enumeration failed"+Context(c));}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Constructor probe reached an unsupported source dependency");
            Need(coldPreserved>0&&signatures>0&&annotations>0&&parameterAnnotations>0,"Constructor fixture missed metadata/cold-class domains: cold="+coldPreserved+", signatures="+signatures+", annotations="+annotations+", parameters="+parameterAnnotations);success=true;
            return new long[]{cases.Length,records,signatures,annotations,parameterAnnotations,coldPreserved,errors,workers,workers*iterations};
        } finally {
            int release=Fn<Release>(dll,"boom_release_trace_pool")();if(success)Need(release==0,"Reflection image retained frames");
            if(heap!=IntPtr.Zero){int cleanup=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(cleanup==1,"Reflection heap cleanup failed");}
            foreach(var p in allocated)Marshal.FreeHGlobal(p);if(success){NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
        }
    }
}
