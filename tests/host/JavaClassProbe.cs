using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Development host. Source-shaped loader/module objects are not constructor or
// module-bootstrap proof. All mirror/query/allocation/GC behavior executes ASM.
public static class BoomJavaClassProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr h,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr ctx,IntPtr pool,uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint TypeId(IntPtr ctx,IntPtr pool,IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Identity(IntPtr pool,uint id,IntPtr value,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Seal(IntPtr pool,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Query(IntPtr ctx,IntPtr args,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassName(IntPtr ctx,IntPtr args,IntPtr pool,IntPtr names);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    sealed class Row {public int Id,Kind,Component,Parent,Loader,Module;public string Name;}
    static T Fn<T>(IntPtr module,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static void Need(bool value,string reason){if(!value)throw new Exception(reason);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,37);Marshal.WriteInt32(c,8,73);}
    static IntPtr Context(){IntPtr p=Marshal.AllocHGlobal(32);Reset(p);return p;}
    static string Primitive(string value){switch(value){case "Z":return "boolean";case "B":return "byte";case "C":return "char";case "S":return "short";case "I":return "int";case "J":return "long";case "F":return "float";case "D":return "double";default:return "void";}}
    static string Text(IntPtr value,IntPtr namePool){
        Need(value!=IntPtr.Zero&&Marshal.ReadIntPtr(value,-8)==Marshal.ReadIntPtr(namePool,32),"Class name is not a normal source String");
        IntPtr literal=Marshal.ReadIntPtr(namePool,24),data=Marshal.ReadIntPtr(value);int coder=Marshal.ReadByte(value,Marshal.ReadInt32(literal,52));
        long bytes=Marshal.ReadInt64(data,-16);Need(Marshal.ReadInt64(data,-8)==264&&coder<=1&&bytes>=0&&bytes<=131070&&(bytes%(1<<coder))==0,"Class name value/coder differs");
        var chars=new char[checked((int)(bytes>>coder))];for(int i=0;i<chars.Length;i++)chars[i]=coder==0?(char)Marshal.ReadByte(data,i):(char)unchecked((ushort)Marshal.ReadInt16(data,i*2));return new string(chars);
    }
    public static long[] Run(string runtime,string dll,string directory,int moduleType,string componentName=null,string loaderName=null,string moduleName=null,string nameName=null) {
        IntPtr library=NativeLibrary.Load(runtime),image=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,args=IntPtr.Zero,rootMemory=IntPtr.Zero;
        var destroy=Fn<Destroy>(library,"boom_heap_destroy");
        try {
            image=NativeLibrary.Load(dll);ctx=Context();args=Marshal.AllocHGlobal(16);
            IntPtr pool=NativeLibrary.GetExport(image,"boom_java_class_pool"),roots=Marshal.ReadIntPtr(pool,16),classLayout=Marshal.ReadIntPtr(pool,32);
            var load=Fn<Load>(library,"boom_java_class_load");var type=Fn<TypeId>(library,"boom_java_class_typeid");var query=Fn<Query>(library,"boom_java_class_query");
            var bindLoader=Fn<Identity>(library,"boom_java_class_bind_loader");var bindModule=Fn<Identity>(library,"boom_java_class_bind_module");var seal=Fn<Seal>(library,"boom_java_class_seal");
            var make=Fn<New>(library,"boom_object_new");
            Entry component=componentName==null?null:Fn<Entry>(image,componentName),loaderGetter=loaderName==null?null:Fn<Entry>(image,loaderName),moduleGetter=moduleName==null?null:Fn<Entry>(image,moduleName);
            Entry nameGetter=nameName==null?null:Fn<Entry>(image,nameName);IntPtr namePool=nameGetter==null?IntPtr.Zero:NativeLibrary.GetExport(image,"boom_java_class_name_pool");
            ClassName rawName=nameGetter==null?null:Fn<ClassName>(library,"boom_java_class_name");long nameCalls=0;
            var rows=new List<Row>();var byName=new Dictionary<string,Row>();
            foreach(string line in File.ReadLines(Path.Combine(directory,"types.tsv"))){string[] p=line.Split('\t');var r=new Row{Id=int.Parse(p[0]),Kind=int.Parse(p[1]),Component=int.Parse(p[2]),Parent=int.Parse(p[3]),Loader=int.Parse(p[4]),Module=int.Parse(p[5]),Name=p[6]};rows.Add(r);byName[r.Kind==0?Primitive(r.Name):r.Name.Replace('/','.')]=r;}
            int classId=Marshal.ReadInt32(pool,108);Need(load(ctx,pool,(uint)classId)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==20,"Unbound Class heap was accepted");
            Reset(ctx);heap=Fn<Create>(library,"boom_heap_create")(192*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"Class fixture heap bind failed");
            IntPtr self=load(ctx,pool,(uint)classId);Need(self!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Early java.base Class mirror failed");
            int moduleOffset=Marshal.ReadInt32(pool,100),loaderOffset=Marshal.ReadInt32(pool,96),componentOffset=Marshal.ReadInt32(pool,104);
            Need(Marshal.ReadIntPtr(self,moduleOffset)==IntPtr.Zero&&Marshal.ReadIntPtr(self,loaderOffset)==IntPtr.Zero,"Pre-module Class fields differ");
            Marshal.WriteIntPtr(args,self);Need((long)query(ctx,args,pool,0)==self.ToInt64(),"Class.class.getClass identity differs");
            Reset(ctx);Need(seal(pool,ctx)==0&&Marshal.ReadInt32(ctx)==20,"Class early phase sealed without java.base");
            Row platform=rows.Find(r=>r.Loader!=0);Reset(ctx);Need(load(ctx,pool,(uint)platform.Id)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==20,"Nonbootstrap Class silently received a null loader");
            IntPtr map=NativeLibrary.GetExport(image,"boom_runtime_type_map"),runtimeRows=Marshal.ReadIntPtr(map,16);var layouts=new Dictionary<int,IntPtr>();
            for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr r=IntPtr.Add(runtimeRows,i*40);if(Marshal.ReadInt32(r,20)==0)layouts.Add(Marshal.ReadInt32(r,16),Marshal.ReadIntPtr(r));}
            var loaders=new IntPtr[Marshal.ReadInt32(pool,84)];
            foreach(string line in File.ReadLines(Path.Combine(directory,"loaders.tsv"))){string[] p=line.Split('\t');int id=int.Parse(p[0]);Reset(ctx);loaders[id]=make(heap,layouts[int.Parse(p[1])],ctx);Need(loaders[id]!=IntPtr.Zero&&bindLoader(pool,(uint)id,loaders[id],ctx)==1&&Marshal.ReadInt32(ctx)==0,"Source loader binding failed");}
            int moduleCount=Marshal.ReadInt32(pool,88);IntPtr moduleLoaders=Marshal.ReadIntPtr(pool,128);var modules=new IntPtr[moduleCount];
            for(int id=0;id<moduleCount;id++){Reset(ctx);modules[id]=make(heap,layouts[moduleType],ctx);Marshal.WriteIntPtr(modules[id],Marshal.ReadInt32(pool,136),loaders[Marshal.ReadInt32(moduleLoaders,id*4)]);
                Need(bindModule(pool,(uint)id,modules[id],ctx)==1&&Marshal.ReadInt32(ctx)==0,"Source module identity binding failed: "+id);}
            Need(Marshal.ReadIntPtr(self,moduleOffset)==modules[0],"Early Class module was not patched");Reset(ctx);Need(seal(pool,ctx)==1&&Marshal.ReadInt32(pool,92)==0,"Class early phase was not sealed");
            const int workers=8;
            if(nameGetter!=null){
                Need(Marshal.ReadIntPtr(self,Marshal.ReadInt32(namePool,8))==IntPtr.Zero,"Class name was eagerly constructed");
                long cold=Marshal.ReadInt64(heap,56);Parallel.For(0,workers,i=>{IntPtr c=Context(),a=Marshal.AllocHGlobal(8);try{Marshal.WriteIntPtr(a,self);IntPtr n=new IntPtr(unchecked((long)nameGetter(c,a)));Need(Marshal.ReadInt32(c)==0&&Text(n,namePool)=="java.lang.Class","Concurrent cold Class.getName differs");}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
                Need(Marshal.ReadInt64(heap,56)==cold+2,"Cold Class name allocated more than one String/value pair");nameCalls+=workers;
            }
            Parallel.For(0,workers,worker=>{IntPtr c=Context(),a=Marshal.AllocHGlobal(8);try{for(int i=worker;i<rows.Count;i+=workers){Row r=rows[i];Reset(c);IntPtr value=load(c,pool,(uint)r.Id);
                Need(value!=IntPtr.Zero&&Marshal.ReadInt32(c)==0&&Marshal.ReadIntPtr(value,-8)==classLayout,"Class normal source layout/tag differs: "+r.Id);
                Need(Marshal.ReadIntPtr(value,moduleOffset)==modules[r.Module]&&Marshal.ReadIntPtr(value,loaderOffset)==loaders[r.Loader],"Class module/loader identity differs");
                Need(Marshal.ReadIntPtr(value,componentOffset)==(r.Component<0?IntPtr.Zero:Marshal.ReadIntPtr(roots,r.Component*8)),"Array Class component differs");
                Need(type(c,pool,value)==r.Id&&Marshal.ReadInt32(c)==0,"Class reverse identity differs");
                if(component!=null){Marshal.WriteIntPtr(a,value);Need(component(c,a)==unchecked((ulong)Marshal.ReadIntPtr(value,componentOffset).ToInt64())&&Marshal.ReadInt32(c)==0,"Original Class.getComponentType differs");
                    Need(loaderGetter(c,a)==unchecked((ulong)loaders[r.Loader].ToInt64())&&moduleGetter(c,a)==unchecked((ulong)modules[r.Module].ToInt64())&&Marshal.ReadInt32(c)==0,"Original Class loader/module getter differs");}
                if(nameGetter!=null){Marshal.WriteIntPtr(a,value);IntPtr n=new IntPtr(unchecked((long)nameGetter(c,a)));string expected=r.Kind==0?Primitive(r.Name):r.Name.Replace('/','.');
                    Need(Marshal.ReadInt32(c)==0&&Text(n,namePool)==expected&&Marshal.ReadIntPtr(value,Marshal.ReadInt32(namePool,8))==n,"Original Class.getName/cache differs: "+r.Id);
                    int canonical=Marshal.ReadInt32(Marshal.ReadIntPtr(namePool,16),r.Id*4),alias=Marshal.ReadInt32(Marshal.ReadIntPtr(namePool,56),canonical*4);
                    if(alias>=0)Need(Marshal.ReadIntPtr(Marshal.ReadIntPtr(Marshal.ReadIntPtr(namePool,48),24),alias*16)==n,"Class name and original String literal canonical identity differ");
                    Need(nameGetter(c,a)==unchecked((ulong)n.ToInt64())&&Marshal.ReadInt32(c)==0,"Warm Class.getName identity differs");}
            }}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            if(nameGetter!=null)nameCalls+=rows.Count*2L;
            long before=Marshal.ReadInt64(heap,48);long queries=0;
            foreach(Row r in rows){Reset(ctx);IntPtr value=Marshal.ReadIntPtr(roots,r.Id*8);Marshal.WriteIntPtr(args,value);
                for(uint op=1;op<=5;op++){ulong expected=op==1?(r.Kind==2?1UL:0):op==2?(r.Kind==3?1UL:0):op==3?(r.Kind==0?1UL:0):op==4?0UL:(r.Parent<0?0UL:unchecked((ulong)Marshal.ReadIntPtr(roots,r.Parent*8).ToInt64()));
                    Need(query(ctx,args,pool,op)==expected&&Marshal.ReadInt32(ctx)==0,"Source Class query differs: "+r.Id+" op="+op);queries++;}
            }
            Need(Marshal.ReadInt64(heap,48)==before,"Hot Class queries allocated");long oracle=0;
            foreach(string line in File.ReadLines(Path.Combine(directory,"oracle.tsv"))){string[] p=line.Split('\t');Marshal.WriteIntPtr(args,Marshal.ReadIntPtr(roots,byName[p[0]].Id*8));Marshal.WriteIntPtr(args,8,Marshal.ReadIntPtr(roots,byName[p[1]].Id*8));Reset(ctx);
                Need(query(ctx,args,pool,6)==ulong.Parse(p[2])&&Marshal.ReadInt32(ctx)==0,"Class assignability differs from JVM: "+line);oracle++;}
            int errors=0;Reset(ctx);IntPtr fake=make(heap,classLayout,ctx);Need(type(ctx,pool,fake)==uint.MaxValue&&Marshal.ReadInt32(ctx)==7,"Unregistered Class-shaped object was accepted");errors++;
            Reset(ctx);Need(type(ctx,pool,IntPtr.Zero)==uint.MaxValue&&Marshal.ReadInt32(ctx)==4,"Null Class receiver accepted");errors++;
            Reset(ctx);Need(query(ctx,IntPtr.Zero,pool,1)==0&&Marshal.ReadInt32(ctx)==7,"Null Class argv accepted");errors++;
            Reset(ctx);Marshal.WriteInt32(ctx,16);Marshal.WriteIntPtr(ctx,16,self);Need(load(ctx,pool,(uint)classId)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==16&&Marshal.ReadIntPtr(ctx,16)==self,"Class load consumed pending Throwable");errors++;
            Reset(ctx);Need(bindLoader(pool,0,self,ctx)==0&&Marshal.ReadInt32(ctx)==7,"Bootstrap loader was replaced");errors++;
            Reset(ctx);IntPtr replacement=make(heap,layouts[moduleType],ctx);Need(bindModule(pool,0,replacement,ctx)==0&&Marshal.ReadInt32(ctx)==7&&Marshal.ReadIntPtr(self,moduleOffset)==modules[0],"Canonical module was replaced");errors++;
            Reset(ctx);IntPtr forged=make(heap,layouts[moduleType],ctx);int nonbootModule=1;while(nonbootModule<moduleCount&&Marshal.ReadInt32(moduleLoaders,nonbootModule*4)==0)nonbootModule++;
            Need(nonbootModule<moduleCount&&bindModule(pool,(uint)nonbootModule,forged,ctx)==0&&Marshal.ReadInt32(ctx)==7,"Module accepted a mismatched loader");errors++;
            int nameErrors=0;long nameRootCount=nameGetter==null?0:Marshal.ReadInt64(NativeLibrary.GetExport(image,"boom_java_class_name_root_count"));IntPtr nameRoots=nameGetter==null?IntPtr.Zero:NativeLibrary.GetExport(image,"boom_java_class_name_roots");
            IntPtr literalPool=NativeLibrary.GetExport(image,"boom_java_string_literal_pool"),literalRoots=Marshal.ReadIntPtr(literalPool,24);long literalRootCount=Marshal.ReadInt32(literalPool,8)*2L;long literalAliases=0;
            if(nameGetter!=null)for(int i=0;i<nameRootCount/2;i++)if(Marshal.ReadInt32(Marshal.ReadIntPtr(namePool,56),i*4)>=0)literalAliases++;
            if(nameGetter!=null){
                Reset(ctx);Need(rawName(ctx,IntPtr.Zero,pool,namePool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Name accepted null argv");nameErrors++;
                Reset(ctx);Marshal.WriteIntPtr(args,IntPtr.Zero);Need(rawName(ctx,args,pool,namePool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==4,"Name accepted null Class");nameErrors++;
                Reset(ctx);Marshal.WriteIntPtr(args,fake);Need(rawName(ctx,args,pool,namePool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Name accepted unregistered Class shape");nameErrors++;
                Reset(ctx);Marshal.WriteInt32(ctx,16);Marshal.WriteIntPtr(ctx,16,self);Marshal.WriteIntPtr(args,self);Need(rawName(ctx,args,pool,namePool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==16&&Marshal.ReadIntPtr(ctx,16)==self&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt32(ctx,8)==73,"Name consumed pending context");nameErrors++;
                Reset(ctx);int off=Marshal.ReadInt32(namePool,8);Marshal.WriteInt32(namePool,8,moduleOffset);Need(rawName(ctx,args,pool,namePool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Name accepted module field as cache");Marshal.WriteInt32(namePool,8,off);nameErrors++;
                Reset(ctx);IntPtr saved=Marshal.ReadIntPtr(self,off);Marshal.WriteIntPtr(self,off,self);Need(rawName(ctx,args,pool,namePool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Name accepted a Class in the String cache");Marshal.WriteIntPtr(self,off,saved);nameErrors++;
            }
            long count=Marshal.ReadInt64(NativeLibrary.GetExport(image,"boom_java_class_root_count"));rootMemory=Marshal.AllocHGlobal(48);
            Marshal.WriteIntPtr(rootMemory,roots);Marshal.WriteInt64(rootMemory,8,count);Marshal.WriteIntPtr(rootMemory,16,nameRoots);Marshal.WriteInt64(rootMemory,24,nameRootCount);Marshal.WriteIntPtr(rootMemory,32,literalRoots);Marshal.WriteInt64(rootMemory,40,literalRootCount);
            var spans=Fn<Collect>(library,"boom_heap_collect_spans");long allocated=Marshal.ReadInt64(heap,56);int spanErrors=0;
            Need(Fn<Collect>(library,"boom_heap_collect")(heap,IntPtr.Zero,1048577)==-1,"Original flat root bound changed");spanErrors++;
            Need(spans(heap,IntPtr.Zero,1)==-1,"Null nonempty root-region array accepted");spanErrors++;
            Need(spans(heap,rootMemory,65537)==-1&&spans(heap,rootMemory,1UL<<32)==-1,"Invalid 64-bit root-region count accepted");spanErrors++;
            Marshal.WriteInt64(rootMemory,8,0x1000001);Need(spans(heap,rootMemory,3)==-1,"Oversized root region accepted");Marshal.WriteInt64(rootMemory,8,count);spanErrors++;
            Need(spans(IntPtr.Zero,rootMemory,3)==-1&&Marshal.ReadInt64(heap,56)==allocated,"Invalid root-region request changed the heap");spanErrors++;
            long expectedLive=rows.Count+loaders.Length-1+moduleCount+nameRootCount;long freed=spans(heap,rootMemory,3);
            Need(freed==allocated-expectedLive&&Marshal.ReadInt64(heap,56)==expectedLive,"Class graph differs after region collection: freed="+freed+" allocated="+allocated+" expected="+expectedLive+" actual="+Marshal.ReadInt64(heap,56));
            Reset(ctx);Need(load(ctx,pool,(uint)classId)==self&&type(ctx,pool,self)==classId,"Canonical Class identity changed after collection");
            if(nameGetter!=null){long warm=Marshal.ReadInt64(heap,48);foreach(Row r in rows){Reset(ctx);IntPtr value=Marshal.ReadIntPtr(roots,r.Id*8);Marshal.WriteIntPtr(args,value);IntPtr n=new IntPtr(unchecked((long)nameGetter(ctx,args)));Need(Marshal.ReadInt32(ctx)==0&&Marshal.ReadIntPtr(value,Marshal.ReadInt32(namePool,8))==n&&Text(n,namePool)==(r.Kind==0?Primitive(r.Name):r.Name.Replace('/','.')),"Class name lost after collection");}Need(Marshal.ReadInt64(heap,48)==warm,"Warm Class names allocated after collection");nameCalls+=rows.Count;}
            return new long[]{rows.Count,queries,oracle,workers,errors,freed,expectedLive,component==null?0:rows.Count*3L,nameCalls,nameErrors,nameRootCount/2,literalAliases,count+nameRootCount+literalRootCount,spanErrors};
        }finally{if(rootMemory!=IntPtr.Zero)Marshal.FreeHGlobal(rootMemory);if(ctx!=IntPtr.Zero)Marshal.FreeHGlobal(ctx);if(args!=IntPtr.Zero)Marshal.FreeHGlobal(args);if(heap!=IntPtr.Zero)destroy(heap);if(image!=IntPtr.Zero)NativeLibrary.Free(image);NativeLibrary.Free(library);}
    }
}
