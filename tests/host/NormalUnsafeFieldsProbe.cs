using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development FFI/allocation fixtures. No managed code executes guest methods.
public static class BoomNormalUnsafeFieldsProbe {
    const ulong Tag=0x55464c4400000000UL;
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Kernel(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Address(IntPtr ctx,IntPtr pool,IntPtr obj,ulong cookie);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong size,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewObject(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr ctx,IntPtr pool,int id);
    static T Fn<T>(IntPtr lib,string n) where T:Delegate {return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,n));}
    static void Need(bool b,string s){if(!b)throw new Exception(s);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,17);Marshal.WriteInt32(c,8,31);}
    static IntPtr Memory(List<IntPtr> memory,int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);memory.Add(p);return p;}
    static IntPtr Copy(List<IntPtr> memory,IntPtr source,int n){IntPtr p=Memory(memory,n);byte[] b=new byte[n];Marshal.Copy(source,b,0,n);Marshal.Copy(b,0,p,n);return p;}
    static string Text(string hex){byte[] bytes=Convert.FromHexString(hex);char[] chars=new char[bytes.Length/2];Buffer.BlockCopy(bytes,0,chars,0,bytes.Length);return new string(chars);}
    sealed class Case { public int Id,Class,Access,Kind,Width;public string Name; public IntPtr ClassObject,NameObject;public ulong Cookie {get{return Tag|(uint)(Id+1);}} }

    public static long[] Run(string runtime,string image,string casesPath,string samplesPath,string nativeName,
        int unsafeId,int singleton,int[] atomics,int[] valueFields,int[] valueCells,string[] entries,int[] inherited) {
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero,other=IntPtr.Zero;
        var memory=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try {
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);Need(heap!=IntPtr.Zero,"Field fixture heap creation failed");
            Need(Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Field source heap binding failed");
            IntPtr pool=NativeLibrary.GetExport(dll,"boom_java_unsafe_field_pool"),classPool=Marshal.ReadIntPtr(pool,24),stringLayout=Marshal.ReadIntPtr(pool,56);
            IntPtr unsafeClass=NativeLibrary.GetExport(dll,"boom_class"+unsafeId),single=NativeLibrary.GetExport(dll,"boom_s"+unsafeId+"_"+singleton);
            IntPtr ctx=Memory(memory,32),args=Memory(memory,32);var ensure=Fn<Ensure>(lib,"boom_class_ensure32");
            var query=Fn<Entry>(dll,nativeName);var kernel=Fn<Kernel>(lib,"boom_java_unsafe_field");var address=Fn<Address>(lib,"boom_java_unsafe_field_address");
            var alloc=Fn<Alloc>(lib,"boom_heap_alloc");var newObject=Fn<NewObject>(lib,"boom_object_new");var mirror=Fn<Mirror>(lib,"boom_java_class_load");
            Need(Marshal.ReadInt32(unsafeClass,8)==0&&Marshal.ReadIntPtr(single)==IntPtr.Zero,"Unsafe source was preinitialized");
            const int workers=8,iterations=2048;
            using(var gate=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);gate.SignalAndWait();Need(ensure(unsafeClass,c)==0&&Marshal.ReadInt32(c)==0,"Original Unsafe initialization failed");}finally{Marshal.FreeHGlobal(c);}
            });
            IntPtr receiver=Marshal.ReadIntPtr(single);Need(receiver!=IntPtr.Zero&&Marshal.ReadInt32(unsafeClass,8)==2,"Unsafe singleton not published by original code");
            Marshal.WriteIntPtr(args,receiver);
            var mirrors=new Dictionary<int,IntPtr>();var strings=new Dictionary<string,IntPtr>(StringComparer.Ordinal);
            Func<int,IntPtr> classOf=id=>{
                if(!mirrors.TryGetValue(id,out IntPtr value)){Reset(ctx);value=mirror(ctx,classPool,id);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Canonical source Class unavailable: "+id);mirrors.Add(id,value);}return value;
            };
            Func<string,bool,IntPtr> stringOf=(name,word)=>{
                foreach(char ch in name)if(ch>255)word=true;
                string key=(word?"W":"L")+name;
                if(strings.TryGetValue(key,out IntPtr old))return old;
                int size=name.Length*(word?2:1);IntPtr bytes=alloc(heap,(ulong)size,0,264);Need(bytes!=IntPtr.Zero,"Field name byte fixture allocation failed");
                for(int i=0;i<name.Length;i++){
                    if(word){Marshal.WriteByte(bytes,2*i,(byte)name[i]);Marshal.WriteByte(bytes,2*i+1,(byte)(name[i]>>8));}
                    else Marshal.WriteByte(bytes,i,(byte)name[i]);
                }
                Reset(ctx);IntPtr value=newObject(heap,stringLayout,ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal field-name String fixture allocation failed");
                Marshal.WriteIntPtr(value,Marshal.ReadInt32(pool,96),bytes);Marshal.WriteByte(value,Marshal.ReadInt32(pool,100),(byte)(word?1:0));strings.Add(key,value);return value;
            };
            var cases=new List<Case>();var byId=new Dictionary<int,Case>();
            foreach(string line in File.ReadLines(casesPath)) {
                string[] p=line.Split('\t');var c=new Case{Id=int.Parse(p[0]),Class=int.Parse(p[1]),Access=int.Parse(p[2]),Kind=int.Parse(p[3]),Width=int.Parse(p[4]),Name=Text(p[6])};
                c.ClassObject=classOf(c.Class);c.NameObject=stringOf(c.Name,(c.Id&1)!=0);cases.Add(c);byId.Add(c.Id,c);
            }
            Need(cases.Count>1000,"Source field coverage unexpectedly small");
            foreach(int id in atomics)Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_class"+id),8)==0,"Field lookup target was initialized before query");
            foreach(Case c in cases) {
                Marshal.WriteIntPtr(args,8,c.ClassObject);Marshal.WriteIntPtr(args,16,c.NameObject);Reset(ctx);long before=Marshal.ReadInt64(heap,48);
                ulong token=query(ctx,args);Need(Marshal.ReadInt32(ctx)==0&&token==c.Cookie,"Original field lookup differs: "+c.Class+"."+c.Name+", kind="+Marshal.ReadInt32(ctx));
                Need(Marshal.ReadInt64(heap,48)==before,"Field query allocated on the game heap");
            }
            foreach(int id in atomics)Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_class"+id),8)==0,"Metadata query ran target class initializer");
            using(var gate=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);gate.SignalAndWait();foreach(int id in atomics){
                    int status=ensure(NativeLibrary.GetExport(dll,"boom_class"+id),c);IntPtr diagnostic=NativeLibrary.GetExport(dll,"boom_diagnostic_pool");
                    Need(status==0&&Marshal.ReadInt32(c)==0,"Original atomic class initializer failed: class="+id+", status="+status+", kind="+Marshal.ReadInt32(c)+", diagnostic="+Marshal.ReadInt32(diagnostic,32));
                }}finally{Marshal.FreeHGlobal(c);}
            });
            for(int i=0;i<atomics.Length;i++) {
                IntPtr cell=NativeLibrary.GetExport(dll,"boom_s"+atomics[i]+"_"+valueCells[i]);
                Need(unchecked((ulong)Marshal.ReadInt64(cell))==byId[valueFields[i]].Cookie,"Original atomic initializer stored wrong field cookie");
            }
            var layouts=new Dictionary<int,IntPtr>();IntPtr runtimeMap=Marshal.ReadIntPtr(pool,32),runtimeRows=Marshal.ReadIntPtr(runtimeMap,16);
            for(int i=0;i<Marshal.ReadInt32(runtimeMap,8);i++) {
                IntPtr row=IntPtr.Add(runtimeRows,40*i);if(Marshal.ReadInt32(row,20)==0)layouts.Add(Marshal.ReadInt32(row,16),Marshal.ReadIntPtr(row));
            }
            var samples=new List<int[]>();var objects=new List<IntPtr>();int shifted=0;
            foreach(string line in File.ReadLines(samplesPath)) {
                string[] p=line.Split('\t');int[] s=Array.ConvertAll(p,int.Parse);samples.Add(s);Reset(ctx);
                IntPtr obj=newObject(heap,layouts[s[1]],ctx);Need(obj!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Source layout fixture failed");objects.Add(obj);
                Reset(ctx);IntPtr actual=address(ctx,pool,obj,byId[s[0]].Cookie);Need(Marshal.ReadInt32(ctx)==0&&actual==IntPtr.Add(obj,s[2]),"Receiver-relative source field address differs");
                if(s[4]!=0)Marshal.WriteIntPtr(actual,obj);
                else if(s[3]==1)Marshal.WriteByte(actual,0x5a);
                else if(s[3]==2)Marshal.WriteInt16(actual,0x1234);
                else if(s[3]==4)Marshal.WriteInt32(actual,0x12345678);
                else Marshal.WriteInt64(actual,0x1234567876543210L);
                Need(address(ctx,pool,obj,byId[s[0]].Cookie)==actual&&Marshal.ReadInt32(ctx)==0,"Field cookie changed after a field store");shifted+=s[5];
            }
            int javaCases=0;
            for(int type=0;type<atomics.Length;type++) {
                var ctor=Fn<Entry>(dll,entries[2*type]);var getter=Fn<Entry>(dll,entries[2*type+1]);Case field=byId[valueFields[type]];
                foreach(int value in (type==0?new[]{0,1,-1,int.MinValue,int.MaxValue,0x12345678}:new[]{0,1})) {
                    Reset(ctx);IntPtr obj=newObject(heap,layouts[atomics[type]],ctx);Need(obj!=IntPtr.Zero,"Atomic storage fixture allocation failed");
                    Marshal.WriteIntPtr(args,obj);Marshal.WriteInt64(args,8,unchecked((uint)value));Reset(ctx);ctor(ctx,args);Need(Marshal.ReadInt32(ctx)==0,"Original atomic constructor failed");
                    Reset(ctx);ulong result=getter(ctx,args);Need(Marshal.ReadInt32(ctx)==0&&unchecked((uint)result)==unchecked((uint)value),"Original atomic getter differs");
                    Reset(ctx);IntPtr slot=address(ctx,pool,obj,field.Cookie);Need(slot!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Atomic field address unavailable");
                    int changed=type==0?value^0x5a5a5a5a:1-value;Marshal.WriteInt32(slot,changed);Reset(ctx);result=getter(ctx,args);
                    Need(Marshal.ReadInt32(ctx)==0&&unchecked((uint)result)==unchecked((uint)changed),"Original getter did not observe mapped field store");javaCases++;
                }
            }
            Marshal.WriteIntPtr(args,receiver);
            long parallelBefore=Marshal.ReadInt64(heap,48);
            Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(24);try{
                    Marshal.WriteIntPtr(a,receiver);
                    for(int i=0;i<iterations;i++){
                        Case item=cases[(w*iterations+i)%cases.Count];Marshal.WriteIntPtr(a,8,item.ClassObject);Marshal.WriteIntPtr(a,16,item.NameObject);Reset(c);
                        Need(query(c,a)==item.Cookie&&Marshal.ReadInt32(c)==0,"Concurrent field lookup differs");
                    }
                }finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
            });
            Need(Marshal.ReadInt64(heap,48)==parallelBefore,"Parallel field queries allocated");
            int errors=0;Case first=cases[0];
            Marshal.WriteIntPtr(args,8,first.ClassObject);Marshal.WriteIntPtr(args,16,first.NameObject);
            Action<int,Func<ulong>> failure=(kind,call)=>{Reset(ctx);Need(call()==0&&Marshal.ReadInt32(ctx)==kind,"Field error kind differs, expected="+kind+", actual="+Marshal.ReadInt32(ctx));errors++;};
            Reset(ctx);Marshal.WriteInt32(ctx,99);long used=Marshal.ReadInt64(heap,48);
            Need(query(ctx,args)==0&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==17&&Marshal.ReadInt64(heap,48)==used,"Pending field error was overwritten");errors++;
            Need(kernel(IntPtr.Zero,args,pool,0)==0,"Null field context accepted");errors++;
            failure(7,()=>kernel(ctx,IntPtr.Zero,pool,0));failure(7,()=>kernel(ctx,args,IntPtr.Zero,0));failure(7,()=>kernel(ctx,args,pool,1));
            Marshal.WriteIntPtr(args,IntPtr.Zero);failure(4,()=>query(ctx,args));Marshal.WriteIntPtr(args,receiver);
            IntPtr wrong=alloc(heap,8,0,264);Marshal.WriteIntPtr(args,wrong);failure(7,()=>query(ctx,args));Marshal.WriteIntPtr(args,receiver);
            Marshal.WriteIntPtr(args,8,IntPtr.Zero);failure(4,()=>query(ctx,args));Marshal.WriteIntPtr(args,8,first.NameObject);failure(7,()=>query(ctx,args));Marshal.WriteIntPtr(args,8,first.ClassObject);
            Marshal.WriteIntPtr(args,16,IntPtr.Zero);failure(4,()=>query(ctx,args));Marshal.WriteIntPtr(args,16,wrong);failure(7,()=>query(ctx,args));
            foreach(string name in new[]{"","__boom_missing_field__","\0","\ud800","value\0"}) {Marshal.WriteIntPtr(args,16,stringOf(name,true));failure(23,()=>query(ctx,args));}
            Case parent=byId[inherited[0]];Marshal.WriteIntPtr(args,8,classOf(inherited[1]));Marshal.WriteIntPtr(args,16,parent.NameObject);failure(23,()=>query(ctx,args));
            IntPtr malformed=stringOf("__boom_bad_coder__",false);int coder=Marshal.ReadInt32(pool,100);Marshal.WriteByte(malformed,coder,2);
            Marshal.WriteIntPtr(args,8,first.ClassObject);Marshal.WriteIntPtr(args,16,malformed);failure(7,()=>query(ctx,args));Marshal.WriteByte(malformed,coder,0);
            Marshal.WriteIntPtr(args,16,first.NameObject);
            foreach(int offset in new[]{0,4,8,12,88,92,96,100,104,108,112,120}) {
                IntPtr clone=Copy(memory,pool,128);Marshal.WriteInt32(clone,offset,-1);failure(7,()=>kernel(ctx,args,clone,0));
            }
            foreach(int offset in new[]{16,24,32,40,48,56,64,72,80}) {
                IntPtr clone=Copy(memory,pool,128);Marshal.WriteIntPtr(clone,offset,IntPtr.Zero);failure(7,()=>kernel(ctx,args,clone,0));
            }
            int[] sample=samples[0];IntPtr sampleObject=objects[0];Case sampleCase=byId[sample[0]];
            failure(4,()=>unchecked((ulong)address(ctx,pool,IntPtr.Zero,sampleCase.Cookie).ToInt64()));
            foreach(ulong token in new[]{0UL,Tag,Tag|(uint)(Marshal.ReadInt32(pool,12)+1),0x1234000000000001UL})
                failure(7,()=>unchecked((ulong)address(ctx,pool,sampleObject,token).ToInt64()));
            failure(7,()=>unchecked((ulong)address(ctx,pool,wrong,sampleCase.Cookie).ToInt64()));
            Case staticCase=cases.Find(c=>(c.Access&8)!=0);failure(20,()=>unchecked((ulong)address(ctx,pool,sampleObject,staticCase.Cookie).ToInt64()));
            other=Fn<Create>(lib,"boom_heap_create")(1024*1024);Need(other!=IntPtr.Zero,"Foreign heap fixture failed");
            Reset(ctx);IntPtr foreign=newObject(other,layouts[sample[1]],ctx);Need(foreign!=IntPtr.Zero,"Foreign object fixture failed");
            failure(7,()=>unchecked((ulong)address(ctx,pool,foreign,sampleCase.Cookie).ToInt64()));
            // Mutate copied immutable metadata, never the linked image.
            int pageId=sampleCase.Id>>10,recordOffset=(sampleCase.Id&1023)*64,pageCount=Marshal.ReadInt32(pool,92);
            IntPtr directory=Marshal.ReadIntPtr(pool,80),originalPage=Marshal.ReadIntPtr(directory,pageId*8),metadataRecord=IntPtr.Add(originalPage,recordOffset);
            foreach(int offset in new[]{0,4,8,12,16,20,24,28,40,48,52,56}) {
                IntPtr clone=Copy(memory,pool,128),dirs=Copy(memory,directory,pageCount*8),page=Memory(memory,1024*64),record=IntPtr.Add(page,recordOffset);
                byte[] data=new byte[64];Marshal.Copy(metadataRecord,data,0,64);Marshal.Copy(data,0,record,64);Marshal.WriteIntPtr(dirs,pageId*8,page);Marshal.WriteIntPtr(clone,80,dirs);
                Marshal.WriteInt32(record,offset,-1);failure(7,()=>unchecked((ulong)address(ctx,clone,sampleObject,sampleCase.Cookie).ToInt64()));
            }
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Field-only probe reached an unimplemented dependency");
            return new long[]{workers,cases.Count,mirrors.Count,samples.Count,shifted,workers*iterations,errors,javaCases,atomics.Length,atomics.Length,strings.Count};
        } finally {
            if(other!=IntPtr.Zero)Need(destroy(other)==1,"Foreign field heap cleanup failed");
            if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Field heap cleanup failed");
            for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);
            if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);
        }
    }
}
