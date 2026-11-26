using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development caller only. Original Java initializers/getters and every guest
// operation execute generated assembly. No class state is premarked complete.
public static class BoomClassBootstrapProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr descriptor,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Kernel(IntPtr ctx,IntPtr argv,IntPtr pool,int operation);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Bytes(IntPtr heap,int count,uint kind,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr spans,ulong count);
    static T Fn<T>(IntPtr lib,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,37);Marshal.WriteInt32(c,8,73);}
    static IntPtr Memory(List<IntPtr> owned,int bytes){IntPtr p=Marshal.AllocHGlobal(Math.Max(bytes,8));for(int i=0;i<Math.Max(bytes,8);i++)Marshal.WriteByte(p,i,0);owned.Add(p);return p;}
    static string Text(IntPtr value,IntPtr source){
        Need(value!=IntPtr.Zero&&Marshal.ReadIntPtr(value,-8)==Marshal.ReadIntPtr(source,40),"Wrong normal String shape");
        IntPtr data=Marshal.ReadIntPtr(value);int coder=Marshal.ReadByte(value,Marshal.ReadInt32(source,52));
        Need(coder<=1&&Marshal.ReadInt64(data,-8)==264,"Wrong String byte array/coder");
        int n=checked((int)Marshal.ReadInt64(data,-16))>>coder;char[] chars=new char[n];
        for(int i=0;i<n;i++)chars[i]=coder==0?(char)Marshal.ReadByte(data,i):(char)unchecked((ushort)Marshal.ReadInt16(data,i*2));return new string(chars);
    }
    static IntPtr String(IntPtr heap,IntPtr source,string text,bool wide,IntPtr c,New make,Bytes bytes){
        foreach(char u in text)if(u>255)wide=true;Reset(c);IntPtr data=bytes(heap,checked(text.Length*(wide?2:1)),8,c);
        Need(data!=IntPtr.Zero&&Marshal.ReadInt32(c)==0,"Name bytes allocation failed");
        for(int i=0;i<text.Length;i++){if(wide)Marshal.WriteInt16(data,i*2,unchecked((short)text[i]));else Marshal.WriteByte(data,i,(byte)text[i]);}
        IntPtr p=make(heap,Marshal.ReadIntPtr(source,40),c);Need(p!=IntPtr.Zero&&Marshal.ReadInt32(c)==0,"Name String allocation failed");
        Marshal.WriteIntPtr(p,data);Marshal.WriteByte(p,Marshal.ReadInt32(source,52),(byte)(wide?1:0));return p;
    }
    static Dictionary<int,Entry> Entries(IntPtr lib,string path){var result=new Dictionary<int,Entry>();foreach(string row in File.ReadAllLines(path)){string[] p=row.Split('\t');result.Add(int.Parse(p[0]),Fn<Entry>(lib,p[1]));}return result;}
    public static long[] Run(string runtime,string image,string directory,int classId,int emptyField,int serialField,string nameSymbol,string componentSymbol){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var owned=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try {
            dll=NativeLibrary.Load(image);IntPtr ctx=Memory(owned,32),argv=Memory(owned,16);
            IntPtr source=NativeLibrary.GetExport(dll,"boom_java_string_literal_pool"),pool=NativeLibrary.GetExport(dll,"boom_java_class_bootstrap_pool");
            IntPtr classPool=NativeLibrary.GetExport(dll,"boom_java_class_pool"),descriptor=NativeLibrary.GetExport(dll,"boom_class"+classId);
            IntPtr emptyCell=NativeLibrary.GetExport(dll,"boom_s"+classId+"_"+emptyField),serialCell=NativeLibrary.GetExport(dll,"boom_s"+classId+"_"+serialField);
            Need(Marshal.ReadInt32(descriptor,8)==0&&Marshal.ReadInt32(pool,8)==0&&Marshal.ReadIntPtr(emptyCell)==IntPtr.Zero&&Marshal.ReadIntPtr(serialCell)==IntPtr.Zero,"Source Class was preinitialized");
            heap=Fn<Create>(lib,"boom_heap_create")(96*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Bootstrap heap bind failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");var kernel=Fn<Kernel>(lib,"boom_java_class_bootstrap");var make=Fn<New>(lib,"boom_object_new");var bytes=Fn<Bytes>(lib,"boom_array_new");
            var native=Entries(dll,Path.Combine(directory,"natives.tsv"));var core=Entries(dll,Path.Combine(directory,"core.tsv"));
            var getName=Fn<Entry>(dll,nameSymbol);var component=Fn<Entry>(dll,componentSymbol);
            const int workers=8,iterations=1024;
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);barrier.SignalAndWait();Need(ensure(descriptor,c)==0&&Marshal.ReadInt32(c)==0,"Original Class initializer failed");}finally{Marshal.FreeHGlobal(c);}
            });
            Need(Marshal.ReadInt32(descriptor,8)==2&&Marshal.ReadInt32(pool,8)==2,"Source initializer/registration not published");
            IntPtr empty=Marshal.ReadIntPtr(emptyCell),serial=Marshal.ReadIntPtr(serialCell);
            Need(empty!=IntPtr.Zero&&serial!=IntPtr.Zero&&empty!=serial&&Marshal.ReadInt64(empty,-16)==0&&Marshal.ReadInt64(serial,-16)==0,"Original static empty arrays differ");
            var expected=new Dictionary<string,int>();foreach(string row in File.ReadAllLines(Path.Combine(directory,"primitives.tsv"))){string[] p=row.Split('\t');expected.Add(p[0],int.Parse(p[1]));}
            var refs=new List<IntPtr>();var arguments=new List<IntPtr>();var canonical=new Dictionary<string,IntPtr>();int javaCalls=1;
            foreach(var t in expected){
                IntPtr identity=IntPtr.Zero;
                foreach(bool wide in new[]{false,true}){
                    IntPtr text=String(heap,source,t.Key,wide,ctx,make,bytes),args=Memory(owned,8);refs.Add(text);Marshal.WriteIntPtr(args,text);
                    Reset(ctx);IntPtr value=native[10](ctx,args);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Primitive lookup failed: "+t.Key);
                    IntPtr roots=Marshal.ReadIntPtr(classPool,16);Need(Marshal.ReadIntPtr(roots,t.Value*8)==value,"Primitive canonical slot differs");
                    if(identity==IntPtr.Zero)identity=value;else Need(identity==value,"Wide/Latin primitive identity differs");
                    arguments.Add(args);Marshal.WriteIntPtr(argv,value);Reset(ctx);Need(core[3](ctx,argv).ToInt64()==1&&Marshal.ReadInt32(ctx)==0,"Primitive flag differs");
                    Reset(ctx);Need(native[11](ctx,argv)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Primitive assertion default differs");
                    Reset(ctx);Need(Text(getName(ctx,argv),source)==t.Key&&Marshal.ReadInt32(ctx)==0,"Original Class.getName differs");javaCalls++;
                }canonical.Add(t.Key,identity);
            }
            int wrappers=0;
            foreach(string row in File.ReadAllLines(Path.Combine(directory,"wrappers.tsv"))){
                string[] p=row.Split('\t');IntPtr d=NativeLibrary.GetExport(dll,p[1]),cell=NativeLibrary.GetExport(dll,p[2]);
                Need(Marshal.ReadInt32(d,8)==0&&Marshal.ReadIntPtr(cell)==IntPtr.Zero,"Wrapper class was preinitialized");Reset(ctx);
                Need(ensure(d,ctx)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadIntPtr(cell)==canonical[p[0]],"Original primitive wrapper TYPE initialization failed: "+p[0]);wrappers++;javaCalls++;
            }
            Marshal.WriteIntPtr(argv,empty);Reset(ctx);IntPtr arrayClass=core[0](ctx,argv);Need(arrayClass!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Empty array getClass failed");
            Marshal.WriteIntPtr(argv,arrayClass);Reset(ctx);IntPtr classMirror=component(ctx,argv);Need(classMirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Original component getter failed");javaCalls++;
            Marshal.WriteIntPtr(argv,classMirror);Reset(ctx);Need(component(ctx,argv)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Non-array component differs");javaCalls++;
            Reset(ctx);Need(Text(getName(ctx,argv),source)=="java.lang.Class"&&Marshal.ReadInt32(ctx)==0,"Class name differs after source initialization");javaCalls++;
            Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{for(int i=0;i<iterations;i++){
                    int n=(i+w)%arguments.Count;Reset(c);IntPtr p=native[10](c,arguments[n]);Need(p!=IntPtr.Zero&&Marshal.ReadInt32(c)==0,"Parallel primitive lookup failed");
                    Need(ensure(descriptor,c)==0&&Marshal.ReadInt32(c)==0,"Warm source initialization failed");
                }}finally{Marshal.FreeHGlobal(c);}
            });
            int errors=0;
            foreach(string invalid in new[]{"","Integer","java.lang.Integer","INT","int\0","中文","\ud800"}){
                IntPtr value=String(heap,source,invalid,false,ctx,make,bytes);refs.Add(value);Marshal.WriteIntPtr(argv,value);Reset(ctx);
                Need(native[10](ctx,argv)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==19,"Unknown primitive did not retain ClassNotFoundException kind");errors++;
            }
            Marshal.WriteIntPtr(argv,IntPtr.Zero);Reset(ctx);Need(native[10](ctx,argv)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==4,"Null primitive name accepted");errors++;
            Reset(ctx);Marshal.WriteInt32(ctx,99);long before=Marshal.ReadInt64(heap,56);Need(native[10](ctx,argv)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt64(heap,56)==before,"Pending bootstrap error overwritten");errors++;
            Need(kernel(IntPtr.Zero,argv,pool,0)==IntPtr.Zero,"Null bootstrap context accepted");errors++;
            IntPtr copy=Memory(owned,80);byte[] metadata=new byte[80];Marshal.Copy(pool,metadata,0,80);
            foreach(int offset in new[]{0,4,12,48,52,56,60,64,68,72}){
                Marshal.Copy(metadata,0,copy,80);Marshal.WriteInt32(copy,offset,offset==0?7:12345);Reset(ctx);
                Need(kernel(ctx,argv,copy,0)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Bad bootstrap metadata accepted: "+offset);errors++;
            }
            Marshal.Copy(metadata,0,copy,80);Marshal.WriteInt32(copy,8,0);Reset(ctx);Need(kernel(ctx,argv,copy,10)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==20,"Unregistered query accepted");errors++;
            IntPtr table=Memory(owned,240);byte[] tableBytes=new byte[240];Marshal.Copy(Marshal.ReadIntPtr(pool,32),tableBytes,0,240);
            foreach(int offset in new[]{0,4,8,16,20}){
                Marshal.Copy(metadata,0,copy,80);Marshal.WriteInt32(copy,8,0);Marshal.Copy(tableBytes,0,table,240);Marshal.WriteIntPtr(copy,32,table);
                if(offset==20)Marshal.WriteInt32(table,offset,1);else if(offset==8)Marshal.WriteIntPtr(table,offset,IntPtr.Zero);else Marshal.WriteInt32(table,offset,0);
                Reset(ctx);Need(kernel(ctx,argv,copy,0)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7&&Marshal.ReadInt32(copy,8)==0,"Invalid AOT native table published");errors++;
            }
            Marshal.Copy(metadata,0,copy,80);Marshal.WriteInt32(copy,56,1);Marshal.WriteIntPtr(argv,classMirror);Reset(ctx);
            Need(kernel(ctx,argv,copy,11).ToInt64()==1&&Marshal.ReadInt32(ctx)==0,"System assertion configuration ignored");
            Marshal.WriteIntPtr(argv,arrayClass);Reset(ctx);Need(kernel(ctx,argv,copy,11)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Array assertion status differs");
            IntPtr roots_=Memory(owned,refs.Count*8);for(int i=0;i<refs.Count;i++)Marshal.WriteIntPtr(roots_,i*8,refs[i]);IntPtr spans=Memory(owned,80);
            Marshal.WriteIntPtr(spans,roots_);Marshal.WriteInt64(spans,8,refs.Count);
            Marshal.WriteIntPtr(spans,16,Marshal.ReadIntPtr(classPool,16));Marshal.WriteInt64(spans,24,Marshal.ReadInt32(classPool,12));
            Marshal.WriteIntPtr(spans,32,NativeLibrary.GetExport(dll,"boom_probe_static_roots"));Marshal.WriteInt64(spans,40,Marshal.ReadInt64(NativeLibrary.GetExport(dll,"boom_probe_static_root_count")));
            Marshal.WriteIntPtr(spans,48,Marshal.ReadIntPtr(source,24));Marshal.WriteInt64(spans,56,Marshal.ReadInt64(NativeLibrary.GetExport(dll,"boom_java_string_literal_root_count")));
            Marshal.WriteIntPtr(spans,64,NativeLibrary.GetExport(dll,"boom_java_class_name_roots"));Marshal.WriteInt64(spans,72,Marshal.ReadInt64(NativeLibrary.GetExport(dll,"boom_java_class_name_root_count")));
            for(int i=0;i<64;i++)String(heap,source,"unrooted bootstrap test",false,ctx,make,bytes);
            long garbage=Fn<Collect>(lib,"boom_heap_collect_spans")(heap,spans,5);Need(garbage>=128&&Marshal.ReadIntPtr(emptyCell)==empty&&Marshal.ReadIntPtr(serialCell)==serial,"Source Class roots or garbage reclamation differ");
            for(int i=0;i<arguments.Count;i++){Reset(ctx);Need(native[10](ctx,arguments[i])!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Primitive identity lost after collection");}
            Need(destroy(heap)==1,"Bootstrap heap cleanup failed");heap=IntPtr.Zero;
            return new long[]{workers,workers*iterations,expected.Count,wrappers,javaCalls,errors,garbage};
        }finally{if(heap!=IntPtr.Zero)destroy(heap);for(int i=owned.Count-1;i>=0;i--)Marshal.FreeHGlobal(owned[i]);if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
    }
}
