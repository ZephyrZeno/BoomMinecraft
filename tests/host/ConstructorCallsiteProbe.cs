// Development FFI. Allocation, conversions, initialization and source Java
// constructor bodies execute ASM. Loader/module and input boxes are fixtures.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomConstructorCallsiteProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong n,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int IdentityBind(IntPtr pool,uint id,IntPtr value,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassLoad(IntPtr ctx,IntPtr pool,uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NativeEntry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Call(IntPtr ctx,IntPtr args,IntPtr site,IntPtr pool,IntPtr phase);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr dll,string n)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,n));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static int I(JsonElement e,string k){return e.GetProperty(k).GetInt32();}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    static ulong Bits(IntPtr p,int width){return width==8?unchecked((ulong)Marshal.ReadInt64(p)):width==4?unchecked((uint)Marshal.ReadInt32(p)):width==2?unchecked((ushort)Marshal.ReadInt16(p)):Marshal.ReadByte(p);}
    static ulong Mask(int width){return width==8?ulong.MaxValue:(1UL<<(width*8))-1;}
    public static long[] Run(string runtime,string image,string configuration,string boxesPath,string oracle){return RunCore(runtime,image,configuration,boxesPath,oracle,null);}
    public static long[] RunNative(string runtime,string image,string configuration,string boxesPath,string oracle,string bindings){return RunCore(runtime,image,configuration,boxesPath,oracle,bindings);}
    static long[] RunCore(string runtime,string image,string configuration,string boxesPath,string oracle,string bindings){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        using var boxesDoc=JsonDocument.Parse(File.ReadAllText(boxesPath));var boxes=boxesDoc.RootElement.GetProperty("boxes").EnumerateArray().ToArray();
        using var bindingDoc=bindings==null?null:JsonDocument.Parse(File.ReadAllText(bindings));bool nativeMode=bindingDoc!=null;
        var cases=s.GetProperty("cases").EnumerateArray().ToArray();var rows=File.ReadAllLines(oracle).Select(l=>l.Split('\t').Select(ulong.Parse).ToArray()).ToArray();
        Need(cases.Length==13&&rows.Length==456&&boxes.Length==8,"Source constructor coverage differs");
        IntPtr lib=NativeLibrary.Load(runtime),dll=NativeLibrary.Load(image),heap=IntPtr.Zero;var owned=new List<IntPtr>();bool success=false;
        IntPtr Memory(int n){var p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);owned.Add(p);return p;}
        try{
            var ctx=Memory(32);var phase=Memory(4);heap=Fn<Create>(lib,"boom_heap_create")(256UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Source constructor heap bind failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");foreach(var id in s.GetProperty("source_class_roots").EnumerateArray())Need(ensure(NativeLibrary.GetExport(dll,"boom_class"+id.GetInt32()),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Constructor VM prerequisite failed");
            var cp=NativeLibrary.GetExport(dll,"boom_java_class_pool");var map=Marshal.ReadIntPtr(cp,40);var mapRows=Marshal.ReadIntPtr(map,16);var allocate=Fn<New>(lib,"boom_object_new");var alloc=Fn<Alloc>(lib,"boom_heap_alloc");
            IntPtr Shape(int id,int kind){for(int i=0;i<Marshal.ReadInt32(map,8);i++){var r=IntPtr.Add(mapRows,40*i);if(Marshal.ReadInt32(r,16)==id&&Marshal.ReadInt32(r,20)==kind)return Marshal.ReadIntPtr(r);}throw new Exception("Constructor source shape missing: "+id);}
            var loaders=new Dictionary<int,IntPtr>{{0,IntPtr.Zero}};
            foreach(var f in s.GetProperty("fixture_loaders").EnumerateArray()){var value=allocate(heap,Shape(I(f,"type_id"),0),ctx);Need(value!=IntPtr.Zero&&Fn<IdentityBind>(lib,"boom_java_class_bind_loader")(cp,(uint)I(f,"id"),value,ctx)==1,"Constructor loader fixture failed");loaders[I(f,"id")]=value;}
            foreach(var f in s.GetProperty("fixture_modules").EnumerateArray()){
                var value=allocate(heap,Shape(I(f,"module_type"),0),ctx);Need(value!=IntPtr.Zero,"Constructor module fixture failed");Marshal.WriteIntPtr(value,I(f,"loader_offset"),loaders[I(f,"loader")]);
                if(f.GetProperty("name").ValueKind!=JsonValueKind.Null){byte[] text=Encoding.Unicode.GetBytes(f.GetProperty("name").GetString());var name=allocate(heap,Shape(I(s,"string_type"),0),ctx);var bytes=alloc(heap,(ulong)text.Length,0,264);Need(name!=IntPtr.Zero&&bytes!=IntPtr.Zero,"Constructor module name fixture failed");Marshal.Copy(text,0,bytes,text.Length);Marshal.WriteIntPtr(name,I(s,"string_value_offset"),bytes);Marshal.WriteByte(name,I(s,"string_coder_offset"),1);Marshal.WriteIntPtr(value,I(f,"name_offset"),name);}
                Need(Fn<IdentityBind>(lib,"boom_java_class_bind_module")(cp,(uint)I(f,"id"),value,ctx)==1&&Marshal.ReadInt32(ctx)==0,"Constructor module fixture binding failed");
            }
            var boxTable=Memory(192);var boxPool=Memory(48);var pool=Memory(48);var cell=Memory(8);Marshal.WriteIntPtr(cell,heap);
            for(int i=0;i<8;i++){var r=IntPtr.Add(boxTable,24*i);Marshal.WriteInt32(r,I(boxes[i],"class_id"));Marshal.WriteInt32(r,4,i);Marshal.WriteIntPtr(r,8,Shape(I(boxes[i],"class_id"),0));Marshal.WriteInt32(r,16,I(boxes[i],"offset"));Marshal.WriteInt32(r,20,I(boxes[i],"width"));}
            Marshal.WriteInt32(boxPool,unchecked((int)0x564e4342));Marshal.WriteInt32(boxPool,4,1);Marshal.WriteInt32(boxPool,8,8);Marshal.WriteInt32(boxPool,12,24);Marshal.WriteIntPtr(boxPool,16,cell);Marshal.WriteIntPtr(boxPool,24,map);Marshal.WriteIntPtr(boxPool,32,boxTable);
            Marshal.WriteInt32(pool,unchecked((int)0x56494350));Marshal.WriteInt32(pool,4,1);Marshal.WriteIntPtr(pool,8,cell);Marshal.WriteIntPtr(pool,16,map);Marshal.WriteIntPtr(pool,24,boxPool);
            IntPtr sites=IntPtr.Zero;Call invoke=null;var nativeTargets=new Dictionary<IntPtr,Tuple<IntPtr,int>>();var nativeCalls=new long[2];
            if(nativeMode){
                var binding=bindingDoc.RootElement;var targets=binding.GetProperty("targets").EnumerateArray().ToArray();
                var entries=binding.GetProperty("native_symbols").EnumerateArray().Select(x=>Fn<NativeEntry>(dll,x.GetString())).ToArray();
                Need(entries.Length==2&&targets.Length==cases.Length,"Native constructor binding coverage differs");
                var invokePool=NativeLibrary.GetExport(dll,"boom_provider_constructor_invoke_pool");sites=Marshal.ReadIntPtr(invokePool,56);
                var enumeration=Fn<NativeEntry>(dll,s.GetProperty("native_constructor_symbol").GetString());var load=Fn<ClassLoad>(lib,"boom_java_class_load");var enumerationArgs=Memory(16);
                for(int i=0;i<cases.Length;i++){
                    var mirror=load(ctx,cp,(uint)I(cases[i],"class_id"));Need(mirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Native constructor Class load failed");
                    Marshal.WriteIntPtr(enumerationArgs,mirror);Marshal.WriteInt64(enumerationArgs,8,0);var array=enumeration(ctx,enumerationArgs);
                    Need(array!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Native constructor enumeration failed");IntPtr ctor=IntPtr.Zero;
                    for(int n=0;n<Marshal.ReadInt32(array,-20);n++){var obj=Marshal.ReadIntPtr(array,n*8);if(Marshal.ReadInt32(obj,I(binding,"slot_offset"))==I(targets[i],"slot")){ctor=obj;break;}}
                    var site=Marshal.ReadIntPtr(sites,I(targets[i],"record_index")*16);Need(ctor!=IntPtr.Zero&&site!=IntPtr.Zero&&Marshal.ReadInt32(site,56)==I(cases[i],"method_id"),"Original native constructor target not ready");
                    nativeTargets.Add(site,Tuple.Create(ctor,i%2));
                }
                invoke=(c,a,site,p,ph)=>{
                    var target=nativeTargets[site];var argv=Marshal.AllocHGlobal(16);try{Marshal.WriteIntPtr(argv,target.Item1);Marshal.WriteIntPtr(argv,8,a);Marshal.WriteInt32(ph,0);System.Threading.Interlocked.Increment(ref nativeCalls[target.Item2]);return entries[target.Item2](c,argv);}finally{Marshal.FreeHGlobal(argv);}
                };
            }else{sites=NativeLibrary.GetExport(dll,"boom_constructor_probe_sites");invoke=Fn<Call>(dll,"boom_constructor_probe_call");}
            var arrayTag=Shape(I(s,"object_array_type"),2);
            IntPtr Args(params IntPtr[] values){var array=alloc(heap,(ulong)values.Length*8,(ulong)values.Length,unchecked((ulong)arrayTag.ToInt64()));Need(array!=IntPtr.Zero,"Constructor args allocation failed");for(int i=0;i<values.Length;i++)Marshal.WriteIntPtr(array,i*8,values[i]);return array;}
            IntPtr Site(int i){return nativeMode?Marshal.ReadIntPtr(sites,I(bindingDoc.RootElement.GetProperty("targets")[i],"record_index")*16):Marshal.ReadIntPtr(sites,i*8);}
            IntPtr Invoke(int i,IntPtr args){Marshal.WriteInt32(phase,99);return invoke(ctx,args,Site(i),pool,phase);}
            var first=Invoke(0,IntPtr.Zero);Need(first!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(phase)==0&&Marshal.ReadIntPtr(first,-8)==Shape(I(cases[0],"class_id"),0),"Original Object constructor failed");
            var second=Invoke(0,Args());Need(second!=IntPtr.Zero&&second!=first&&Marshal.ReadInt32(ctx)==0,"Source constructors returned reused objects");
            int accepted=0,rejected=0,cold=0;
            foreach(var r in rows){
                int from=(int)r[0],to=(int)r[1],at=to+1;var b=boxes[from];var value=allocate(heap,Shape(I(b,"class_id"),0),ctx);Need(value!=IntPtr.Zero,"Source box fixture failed");byte[] bits=BitConverter.GetBytes(r[2]);Marshal.Copy(bits,0,IntPtr.Add(value,I(b,"offset")),I(b,"width"));var args=Args(value);
                var state=NativeLibrary.GetExport(dll,"boom_class"+I(cases[at],"class_id"));int before=Marshal.ReadInt32(state,8);Reset(ctx);var obj=Invoke(at,args);if(before==0&&Marshal.ReadInt32(state,8)==2)cold++;
                Need(Marshal.ReadInt32(ctx)==(int)r[3]&&Marshal.ReadInt32(phase)==0,"Original wrapper constructor context differs: "+from+" -> "+to+" kind="+Marshal.ReadInt32(ctx)+" method="+Marshal.ReadInt32(ctx,8)+" pc="+Marshal.ReadInt32(ctx,4));
                if(r[3]==0){accepted++;var f=cases[at].GetProperty("value");Need(obj!=IntPtr.Zero&&Marshal.ReadIntPtr(obj,-8)==Shape(I(cases[at],"class_id"),0)&&Bits(IntPtr.Add(obj,I(f,"offset")),I(f,"width"))==(r[4]&Mask(I(f,"width"))),"Original Java wrapper constructor did not store the expected field");}
                else{rejected++;Need(obj==IntPtr.Zero,"Rejected source constructor returned an object");}Reset(ctx);
            }
            var entry=cases.Single(c=>c.GetProperty("name").GetString()=="java/util/AbstractMap$SimpleImmutableEntry");int entryIndex=I(entry,"index");
            var pair=Invoke(entryIndex,Args(first,second));Need(pair!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(phase)==0&&Marshal.ReadIntPtr(pair,I(entry.GetProperty("key"),"offset"))==first&&Marshal.ReadIntPtr(pair,I(entry.GetProperty("value"),"offset"))==second,"Original reference-argument constructor failed");
            int bodyErrors=0;foreach(string name in new[]{"java/lang/String","java/lang/StringBuilder","java/util/ArrayList"}){int index=I(cases.Single(c=>c.GetProperty("name").GetString()==name),"index");var obj=Invoke(index,Args(IntPtr.Zero));Need(obj==IntPtr.Zero&&Marshal.ReadInt32(ctx)==4&&(nativeMode||Marshal.ReadInt32(phase)==1),"Original constructor body error was not preserved: "+name+" kind="+Marshal.ReadInt32(ctx));bodyErrors++;Reset(ctx);}
            int preErrors=0;Need(Invoke(5,Args())==IntPtr.Zero&&Marshal.ReadInt32(ctx)==18&&Marshal.ReadInt32(phase)==0,"Argument count failure was classified as constructor body failure");preErrors++;Reset(ctx);
            int sb=I(cases.Single(c=>c.GetProperty("name").GetString()=="java/lang/StringBuilder"),"index");Need(Invoke(sb,Args(first))==IntPtr.Zero&&Marshal.ReadInt32(ctx)==18&&Marshal.ReadInt32(phase)==0,"Reference narrowing was accepted");preErrors++;Reset(ctx);
            if(!nativeMode){
            var corrupt=Memory(64);byte[] siteBytes=new byte[64];Marshal.Copy(Site(5),siteBytes,0,64);foreach(int offset in new[]{0,4,8,12,16,20,60}){Marshal.Copy(siteBytes,0,corrupt,64);Marshal.WriteInt32(corrupt,offset,int.MaxValue);Need(invoke(ctx,Args(first),corrupt,pool,phase)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7&&Marshal.ReadInt32(phase)==0,"Malformed constructor site accepted: "+offset);preErrors++;Reset(ctx);}
            Marshal.Copy(siteBytes,0,corrupt,64);Marshal.WriteIntPtr(corrupt,40,IntPtr.Zero);Need(invoke(ctx,IntPtr.Zero,corrupt,pool,phase)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==20&&Marshal.ReadInt32(phase)==0,"Unlinked constructor target accepted");preErrors++;Reset(ctx);
            }
            if(nativeMode){
                var raw=Fn<NativeEntry>(dll,bindingDoc.RootElement.GetProperty("native_symbols")[0].GetString());var argv=Memory(16);
                Need(raw(ctx,argv)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==4,"Null original Constructor did not preserve NPE");preErrors++;Reset(ctx);
                Marshal.WriteInt32(ctx,18);Need(raw(ctx,argv)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==18,"Native constructor overwrote pending Context error");preErrors++;Reset(ctx);
                Need(raw(IntPtr.Zero,argv)==IntPtr.Zero,"Null native constructor Context was dereferenced");preErrors++;nativeCalls[0]+=3;
            }
            const int workers=8,iterations=64;var sharedBox=allocate(heap,Shape(I(boxes[4],"class_id"),0),ctx);Marshal.WriteInt32(sharedBox,I(boxes[4],"offset"),42);var sharedArgs=Args(sharedBox);var integerCase=cases[5];var output=new IntPtr[workers*iterations];
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var ph=Marshal.AllocHGlobal(4);try{for(int i=0;i<iterations;i++){Reset(c);var obj=invoke(c,sharedArgs,Site(5),pool,ph);Need(obj!=IntPtr.Zero&&Marshal.ReadInt32(c)==0&&Marshal.ReadInt32(ph)==0&&Marshal.ReadInt32(obj,I(integerCase.GetProperty("value"),"offset"))==42,"Concurrent original constructor failed");output[w*iterations+i]=obj;}}finally{Marshal.FreeHGlobal(ph);Marshal.FreeHGlobal(c);}});
            Need(output.Distinct().Count()==output.Length,"Concurrent constructors reused instances");Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Source constructor probe reached an unprovided dependency");
            if(nativeMode)Need(nativeCalls.All(n=>n>0),"Both original native entries were not executed");
            success=true;return new long[]{cases.Length,accepted,rejected,cold,bodyErrors,preErrors,workers,workers*iterations,nativeCalls[0],nativeCalls[1]};
        }finally{int release=Fn<Release>(dll,"boom_release_trace_pool")();if(success)Need(release==0,"Source constructors retained frames");if(heap!=IntPtr.Zero){int freed=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(freed==1,"Source constructor heap cleanup failed");}foreach(var p in owned)Marshal.FreeHGlobal(p);if(success){NativeLibrary.Free(dll);NativeLibrary.Free(lib);}}
    }
}
