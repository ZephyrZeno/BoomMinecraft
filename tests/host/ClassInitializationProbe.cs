using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

// Development host only. Class state machines, initializers, constructors,
// fields, array stores and String factories all execute generated/native MASM.
public static class BoomClassInitializationProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Ensure(IntPtr descriptor,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Body(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint ClassType(IntPtr ctx,IntPtr pool,IntPtr value);
    sealed class Root {public string Name;public IntPtr Descriptor,Values;public int[] Constants;public int Id;public Body ValuesMethod;}
    static T Symbol<T>(IntPtr module,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static IntPtr Context(){IntPtr p=Marshal.AllocHGlobal(32);for(int i=0;i<32;i++)Marshal.WriteByte(p,i,0);return p;}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static string StringUnits(IntPtr text) {
        Need(text!=IntPtr.Zero,"Constant String is null");IntPtr bytes=Marshal.ReadIntPtr(text);int length=checked((int)Marshal.ReadInt64(bytes,-16));byte coder=Marshal.ReadByte(text,12);
        Need(coder<=1&&(coder==0||length%2==0),"Constant String coder differs");StringBuilder value=new StringBuilder();
        for(int i=0;i<length;i+=1<<coder){ushort unit=coder==0?Marshal.ReadByte(bytes,i):unchecked((ushort)Marshal.ReadInt16(bytes,i));value.Append(unit.ToString("x4"));}
        return value.ToString();
    }
    public static long[] Run(string runtime,string generated,string directory,string nameSymbol,string ordinalSymbol,string declaringSymbol=null) {
        IntPtr native=NativeLibrary.Load(runtime),module=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,args=IntPtr.Zero,rootsMemory=IntPtr.Zero;
        Destroy destroy=Symbol<Destroy>(native,"boom_heap_destroy");
        try{
            module=NativeLibrary.Load(generated);Create create=Symbol<Create>(native,"boom_heap_create");Ensure ensure=Symbol<Ensure>(native,"boom_class_ensure32");
            Collect collect=Symbol<Collect>(native,"boom_heap_collect");Bind bind=Symbol<Bind>(module,"boom_java_string_literals_bind_heap");
            Body name=Symbol<Body>(module,nameSymbol),ordinal=Symbol<Body>(module,ordinalSymbol);
            Body declaring=declaringSymbol==null?null:Symbol<Body>(module,declaringSymbol);
            IntPtr classPool=declaring==null?IntPtr.Zero:NativeLibrary.GetExport(module,"boom_java_class_pool");
            ClassType classType=declaring==null?null:Symbol<ClassType>(native,"boom_java_class_typeid");long declaringCalls=0;
            var roots=new List<Root>();var expected=new Dictionary<string,List<string>>();
            foreach(string line in File.ReadLines(Path.Combine(directory,"oracle.tsv"))) {
                string[] p=line.Split('\t');if(!expected.ContainsKey(p[0]))expected[p[0]]=new List<string>();
                Need(int.Parse(p[2])==expected[p[0]].Count,"JVM enum ordinal differs");expected[p[0]].Add(p[1]);
            }
            foreach(string line in File.ReadLines(Path.Combine(directory,"roots.tsv"))) {
                string[] p=line.Split('\t');int id=int.Parse(p[1]);string[] fields=p[3].Split(',');int[] constants=new int[fields.Length];
                for(int i=0;i<fields.Length;i++)constants[i]=int.Parse(fields[i]);
                Root root=new Root{Name=p[0],Id=id,Constants=constants,Descriptor=NativeLibrary.GetExport(module,"boom_class"+id),Values=NativeLibrary.GetExport(module,"boom_s"+id+"_"+p[2])};
                if(p.Length>4)root.ValuesMethod=Symbol<Body>(module,p[4]);
                Need(Marshal.ReadInt32(root.Descriptor,4)==2&&Marshal.ReadInt32(root.Descriptor,8)==0,"Class did not begin uninitialized");
                Need(Marshal.ReadIntPtr(root.Values)==IntPtr.Zero,"Static reference was initialized before active initialization");roots.Add(root);
            }
            string[] constantLines=File.ReadAllLines(Path.Combine(directory,"constants.tsv"));string[] constantExpected=File.ReadAllLines(Path.Combine(directory,"constants-oracle.tsv"));
            Need(constantLines.Length==constantExpected.Length,"Constant reference coverage differs");var constantClasses=new Dictionary<int,IntPtr>();
            foreach(string line in constantLines){string[] p=line.Split('\t');int id=int.Parse(p[1]);
                IntPtr descriptor=NativeLibrary.GetExport(module,"boom_class"+id);constantClasses[id]=descriptor;
                Need(Marshal.ReadInt32(descriptor,8)==0&&Marshal.ReadInt64(NativeLibrary.GetExport(module,"boom_s"+id+"_"+p[3]))==0,"Constant storage was assigned during preparation");}
            heap=create(16*1024*1024);Need(heap!=IntPtr.Zero&&bind(heap)==1,"Initialization heap binding failed");
            Parallel.For(0,8,worker=>{IntPtr context=Context();try{
                for(int i=0;i<roots.Count;i++){Root root=roots[(i+worker)%roots.Count];
                    Need(ensure(root.Descriptor,context)==0&&Marshal.ReadInt32(context)==0&&Marshal.ReadInt32(context,12)==0,"Original class initialization failed: "+root.Name);}
                foreach(IntPtr descriptor in constantClasses.Values)Need(ensure(descriptor,context)==0&&Marshal.ReadInt32(context)==0,"Constant class initialization failed");
            }finally{Marshal.FreeHGlobal(context);}});
            long used=Marshal.ReadInt64(heap,48),enums=0;ctx=Context();args=Marshal.AllocHGlobal(8);var objects=new List<IntPtr>();var canonical=new Dictionary<string,IntPtr>();var cloneRoots=new List<IntPtr>();
            foreach(Root root in roots) {
                Need(Marshal.ReadInt32(root.Descriptor,8)==2,"Class initialization was not published");
                IntPtr array=Marshal.ReadIntPtr(root.Values);Need(array!=IntPtr.Zero,"Original $VALUES was not stored");
                List<string> names=expected[root.Name];Need(Marshal.ReadInt32(array,-20)==names.Count&&root.Constants.Length==names.Count,"Original enum array length differs");
                for(int i=0;i<names.Count;i++){
                    IntPtr value=Marshal.ReadIntPtr(array,i*8),constant=NativeLibrary.GetExport(module,"boom_s"+root.Id+"_"+root.Constants[i]);
                    Need(value!=IntPtr.Zero&&value==Marshal.ReadIntPtr(constant),"Static enum identity differs");objects.Add(value);
                    Marshal.WriteIntPtr(args,value);Need(ordinal(ctx,args)==(ulong)i&&Marshal.ReadInt32(ctx)==0,"Original Enum.ordinal differs");
                    if(declaring!=null){
                        IntPtr cls=new IntPtr(unchecked((long)declaring(ctx,args))),again=new IntPtr(unchecked((long)declaring(ctx,args)));
                        Need(cls!=IntPtr.Zero&&cls==again&&Marshal.ReadInt32(ctx)==0&&classType(ctx,classPool,cls)==root.Id,"Original Enum.getDeclaringClass/Class literal/native identity differs");declaringCalls+=2;
                    }
                    IntPtr text=new IntPtr(unchecked((long)name(ctx,args)));Need(text!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Original Enum.name failed");
                    IntPtr bytes=Marshal.ReadIntPtr(text);int length=checked((int)Marshal.ReadInt64(bytes,-16));byte[] raw=new byte[length];Marshal.Copy(bytes,raw,0,length);
                    Need(Marshal.ReadByte(text,12)==0&&Encoding.ASCII.GetString(raw)==names[i],"Original enum name bytes differ");
                    IntPtr previous;if(canonical.TryGetValue(names[i],out previous))Need(previous==text,"Cross-class literal canonical identity differs");else canonical.Add(names[i],text);
                    enums++;
                }
                if(root.ValuesMethod!=null){
                    IntPtr first=new IntPtr(unchecked((long)root.ValuesMethod(ctx,args))),second=new IntPtr(unchecked((long)root.ValuesMethod(ctx,args)));
                    Need(Marshal.ReadInt32(ctx)==0&&first!=IntPtr.Zero&&second!=IntPtr.Zero&&first!=second&&first!=array&&second!=array,"Original values() did not return independent clones");
                    Need(Marshal.ReadInt64(first,-8)==Marshal.ReadInt64(array,-8)&&Marshal.ReadInt64(second,-8)==Marshal.ReadInt64(array,-8),"Original values() changed the runtime array type");
                    for(int i=0;i<names.Count;i++)Need(Marshal.ReadIntPtr(first,i*8)==Marshal.ReadIntPtr(array,i*8)&&Marshal.ReadIntPtr(second,i*8)==Marshal.ReadIntPtr(array,i*8),"Original values() did not shallow-copy enum references");
                    if(names.Count>0){IntPtr value=Marshal.ReadIntPtr(first);Marshal.WriteIntPtr(first,IntPtr.Zero);Need(Marshal.ReadIntPtr(array)==value&&Marshal.ReadIntPtr(second)==value,"Editing values() changed original/other clone");Marshal.WriteIntPtr(first,value);}
                    cloneRoots.Add(first);cloneRoots.Add(second);
                }
            }
            used=Marshal.ReadInt64(heap,48);
            for(int i=0;i<constantLines.Length;i++){
                string[] p=constantLines[i].Split('\t');IntPtr cell=NativeLibrary.GetExport(module,"boom_s"+p[1]+"_"+p[3]);
                if(p[4]=="Ljava/lang/String;")Need(StringUnits(Marshal.ReadIntPtr(cell))==constantExpected[i],"Original String ConstantValue differs: "+p[0]+"."+p[2]);
                else Need(unchecked((ulong)Marshal.ReadInt64(cell))==ulong.Parse(constantExpected[i],System.Globalization.NumberStyles.HexNumber),"Original numeric ConstantValue differs");
            }
            Parallel.For(0,8,worker=>{IntPtr context=Context();try{for(int n=0;n<1024;n++)foreach(Root root in roots)
                Need(ensure(root.Descriptor,context)==0&&Marshal.ReadInt32(context)==0,"Initialized fast path failed");}finally{Marshal.FreeHGlobal(context);}});
            Need(Marshal.ReadInt64(heap,48)==used,"Warm initialization allocated guest objects");
            IntPtr staticRoots=NativeLibrary.GetExport(module,"boom_probe_static_roots");long staticCount=Marshal.ReadInt64(NativeLibrary.GetExport(module,"boom_probe_static_root_count"));
            IntPtr pool=NativeLibrary.GetExport(module,"boom_java_string_literal_pool"),literalRoots=Marshal.ReadIntPtr(pool,24);long literalCount=Marshal.ReadInt32(pool,8)*2L;
            IntPtr classRoots=declaring==null?IntPtr.Zero:NativeLibrary.GetExport(module,"boom_java_class_roots");long classCount=declaring==null?0:Marshal.ReadInt64(NativeLibrary.GetExport(module,"boom_java_class_root_count"));
            rootsMemory=Marshal.AllocHGlobal(checked((int)((staticCount+literalCount+cloneRoots.Count+classCount)*8)));
            for(int i=0;i<staticCount;i++)Marshal.WriteIntPtr(rootsMemory,i*8,Marshal.ReadIntPtr(staticRoots,i*8));
            for(int i=0;i<literalCount;i++)Marshal.WriteIntPtr(rootsMemory,checked((int)((staticCount+i)*8)),Marshal.ReadIntPtr(literalRoots,i*8));
            for(int i=0;i<cloneRoots.Count;i++)Marshal.WriteIntPtr(rootsMemory,checked((int)((staticCount+literalCount+i)*8)),cloneRoots[i]);
            for(int i=0;i<classCount;i++)Marshal.WriteIntPtr(rootsMemory,checked((int)((staticCount+literalCount+cloneRoots.Count+i)*8)),Marshal.ReadIntPtr(classRoots,i*8));
            Need(collect(heap,rootsMemory,(ulong)(staticCount+literalCount+cloneRoots.Count+classCount))==0,"Initialized static/clone/Class graph was lost during explicit collection");
            int at=0;foreach(Root root in roots)for(int i=0;i<expected[root.Name].Count;i++)Need(Marshal.ReadIntPtr(Marshal.ReadIntPtr(root.Values),i*8)==objects[at++],"Static identity changed after collection");
            GC.KeepAlive(create);GC.KeepAlive(collect);GC.KeepAlive(ensure);GC.KeepAlive(bind);GC.KeepAlive(name);GC.KeepAlive(ordinal);
            return new long[]{roots.Count,enums,used,8*1024L*roots.Count,8,constantClasses.Count,constantLines.Length,cloneRoots.Count,declaringCalls};
        }finally{if(rootsMemory!=IntPtr.Zero)Marshal.FreeHGlobal(rootsMemory);if(args!=IntPtr.Zero)Marshal.FreeHGlobal(args);if(ctx!=IntPtr.Zero)Marshal.FreeHGlobal(ctx);if(heap!=IntPtr.Zero)destroy(heap);if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(native);GC.KeepAlive(destroy);}
    }
}
