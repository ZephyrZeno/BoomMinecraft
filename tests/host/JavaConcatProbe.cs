using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Development kernel caller/oracle. It prepares normal objects, not Java
// constructors or bootstrap initialization. Concatenation executes MASM.
public static class BoomJavaConcatProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Bytes(IntPtr heap,int count,uint kind,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Concat(IntPtr ctx,IntPtr argv,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr spans,ulong count);
    sealed class Case {public IntPtr Pool,Args;public string Expected;public int ArgCount;public Entry Invoke;}
    static T Fn<T>(IntPtr module,string name) where T:Delegate {return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Stage(string directory,string stage){File.AppendAllText(Path.Combine(directory,"execution-stages.log"),stage+"\n");}
    static void Reset(IntPtr ctx){for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);Marshal.WriteInt32(ctx,4,37);Marshal.WriteInt32(ctx,8,73);}
    static IntPtr Memory(List<IntPtr> memory,int bytes){IntPtr p=Marshal.AllocHGlobal(Math.Max(8,bytes));for(int i=0;i<Math.Max(8,bytes);i++)Marshal.WriteByte(p,i,0);memory.Add(p);return p;}
    static char[] ReadChars(BinaryReader r){int n=r.ReadInt32();if(n<0){Need(n==-1,"Bad null text");return null;}Need(n<=2000000,"Case text budget exceeded");char[] c=new char[n];for(int i=0;i<n;i++)c[i]=(char)r.ReadUInt16();return c;}
    static string Text(IntPtr p,IntPtr source){
        Need(p!=IntPtr.Zero&&Marshal.ReadIntPtr(p,-8)==Marshal.ReadIntPtr(source,40),"Concat result has an opaque/wrong String tag");
        IntPtr bytes=Marshal.ReadIntPtr(p);int coder=Marshal.ReadByte(p,Marshal.ReadInt32(source,52));Need(bytes!=IntPtr.Zero&&Marshal.ReadInt64(bytes,-8)==264&&coder<=1,"Concat value/coder differs");
        int n=checked((int)Marshal.ReadInt64(bytes,-16));Need(coder==0||n%2==0,"Odd concat UTF16 payload");char[] chars=new char[n>>coder];uint hash=0;
        for(int i=0;i<chars.Length;i++){chars[i]=coder==0?(char)Marshal.ReadByte(bytes,i):(char)unchecked((ushort)Marshal.ReadInt16(bytes,i*2));hash=unchecked(hash*31+chars[i]);}
        Need(unchecked((uint)Marshal.ReadInt32(p,Marshal.ReadInt32(source,56)))==hash,"Concat Java hash differs");
        Need(Marshal.ReadByte(p,Marshal.ReadInt32(source,60))==(hash==0?1:0),"Concat zero-hash cache differs");return new string(chars);
    }
    static IntPtr MakeString(IntPtr heap,IntPtr source,char[] chars,bool wide,IntPtr ctx,New make,Bytes bytes){
        if(chars==null)return IntPtr.Zero;foreach(char c in chars)if(c>255)wide=true;
        Reset(ctx);IntPtr value=bytes(heap,checked(chars.Length*(wide?2:1)),8,ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Concat input bytes allocation failed");
        for(int i=0;i<chars.Length;i++){if(wide)Marshal.WriteInt16(value,i*2,unchecked((short)chars[i]));else Marshal.WriteByte(value,i,(byte)chars[i]);}
        IntPtr result=make(heap,Marshal.ReadIntPtr(source,40),ctx);Need(result!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Concat input String allocation failed");
        Marshal.WriteIntPtr(result,value);Marshal.WriteByte(result,Marshal.ReadInt32(source,52),(byte)(wide?1:0));return result;
    }
    static long GC(Collect collect,IntPtr heap,IntPtr spans,IntPtr roots,int count){Marshal.WriteIntPtr(spans,roots);Marshal.WriteInt64(spans,8,count);long n=collect(heap,spans,1);Need(n>=0,"Concat graph collection failed");return n;}
    static IntPtr Call(Concat kernel,Case c,IntPtr ctx){return c.Invoke==null?kernel(ctx,c.Args,c.Pool):c.Invoke(ctx,c.Args);}
    public static long[] Run(string runtime,string dll,string directory,bool entries=false){
        IntPtr lib=NativeLibrary.Load(runtime),image=IntPtr.Zero,heap=IntPtr.Zero;var memory=new List<IntPtr>();
        var destroy=Fn<Destroy>(lib,"boom_heap_destroy");try{
            image=NativeLibrary.Load(dll);IntPtr source=NativeLibrary.GetExport(image,"boom_java_string_literal_pool"),ctx=Memory(memory,32),spans=Memory(memory,16);
            IntPtr heapCell=entries?NativeLibrary.GetExport(image,"boom_heap_ptr"):Marshal.ReadIntPtr(NativeLibrary.GetExport(image,"boom_java_platform_properties_pool"),16);
            heap=Fn<Create>(lib,"boom_heap_create")(192*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"Concat heap bind failed");
            var make=Fn<New>(lib,"boom_object_new");var bytes=Fn<Bytes>(lib,"boom_array_new");var concatenate=Fn<Concat>(lib,"boom_java_concat");var allocate=Fn<Alloc>(lib,"boom_heap_alloc");var collect=Fn<Collect>(lib,"boom_heap_collect_spans");
            var cases=new List<Case>();var inputs=new List<IntPtr>();
            using(var r=new BinaryReader(File.OpenRead(Path.Combine(directory,"cases.bin")))){
                Need(r.ReadInt32()==0x4a434f4e,"Bad concat case header");int count=r.ReadInt32();
                for(int c=0;c<count;c++){
                    int argc=r.ReadInt32();IntPtr args=Memory(memory,argc*8);
                    for(int i=0;i<argc;i++){
                        int kind=r.ReadInt32();ulong bits=r.ReadUInt64();char[] text=ReadChars(r);
                        if(kind==5){IntPtr value=MakeString(heap,source,text,bits!=0,ctx,make,bytes);Marshal.WriteIntPtr(args,i*8,value);if(value!=IntPtr.Zero)inputs.Add(value);}
                        else Marshal.WriteInt64(args,i*8,unchecked((long)bits));
                    }
                    int parts=r.ReadInt32();IntPtr rows=Memory(memory,Math.Max(24,parts*24));
                    for(int i=0;i<parts;i++){
                        int kind=r.ReadInt32(),index=r.ReadInt32();char[] text=ReadChars(r);Marshal.WriteInt32(rows,i*24,kind);Marshal.WriteInt32(rows,i*24+4,index);
                        if(kind==0){IntPtr literal=Memory(memory,text.Length*2);for(int j=0;j<text.Length;j++)Marshal.WriteInt16(literal,j*2,unchecked((short)text[j]));Marshal.WriteIntPtr(rows,i*24+8,literal);Marshal.WriteInt64(rows,i*24+16,text.Length);}
                    }
                    IntPtr pool=Memory(memory,80);Marshal.WriteInt32(pool,0,0x4a434e43);Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,8,parts);Marshal.WriteInt32(pool,12,argc);
                    Marshal.WriteIntPtr(pool,16,rows);Marshal.WriteIntPtr(pool,24,heapCell);Marshal.WriteIntPtr(pool,32,Marshal.ReadIntPtr(source,40));
                    for(int i=0;i<4;i++)Marshal.WriteInt32(pool,40+i*4,Marshal.ReadInt32(source,48+i*4));Marshal.WriteInt32(pool,56,1);Marshal.WriteInt32(pool,64,32);
                    cases.Add(new Case {Pool=pool,Args=args,ArgCount=argc});
                }Need(r.BaseStream.Position==r.BaseStream.Length,"Trailing concat input");
            }
            using(var r=new BinaryReader(File.OpenRead(Path.Combine(directory,"oracle.bin")))){
                Need(r.ReadInt32()==0x4a434f55&&r.ReadInt32()==cases.Count,"Bad JVM concat result header");foreach(Case c in cases)c.Expected=new string(ReadChars(r));Need(r.BaseStream.Position==r.BaseStream.Length,"Trailing JVM concat output");
            }
            if(entries){string[] names=File.ReadAllLines(Path.Combine(directory,"entries.txt"));Need(names.Length==cases.Count,"Source entry case count differs");for(int i=0;i<cases.Count;i++)cases[i].Invoke=Fn<Entry>(image,names[i]);}
            IntPtr last=IntPtr.Zero;int index_=0;
            Stage(directory,"calling cases");foreach(Case c in cases){if(entries)Stage(directory,"case "+index_);Reset(ctx);last=Call(concatenate,c,ctx);Need(Marshal.ReadInt32(ctx)==0&&Text(last,source)==c.Expected,"Native/JVM concat differs at case "+index_);index_++;}
            Stage(directory,"calling parallel cases");
            const int workers=8,iterations=1024;Parallel.For(0,workers,w=>{
                IntPtr cc=Marshal.AllocHGlobal(32);try{for(int i=0;i<iterations;i++){Case c=cases[(i+w)%Math.Min(100,cases.Count)];Reset(cc);IntPtr p=Call(concatenate,c,cc);Need(Marshal.ReadInt32(cc)==0&&Text(p,source)==c.Expected,"Parallel concat mismatch");}}finally{Marshal.FreeHGlobal(cc);}
            });
            Stage(directory,"checking guards");int guards=0;Case sample=cases[2];IntPtr bad=Memory(memory,80);byte[] metadata=new byte[80];Marshal.Copy(sample.Pool,metadata,0,80);
            foreach(int offset in new[]{0,4,12,56,60,64,68,72}){
                Marshal.Copy(metadata,0,bad,80);Marshal.WriteInt32(bad,offset,offset==12?201:offset==56?2:7);Reset(ctx);Need(concatenate(ctx,sample.Args,bad)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Bad concat pool accepted: "+offset);guards++;
            }
            Reset(ctx);Marshal.WriteInt32(ctx,99);Need(concatenate(ctx,sample.Args,sample.Pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==37,"Concat overwrote pending error");guards++;
            Need(concatenate(IntPtr.Zero,sample.Args,sample.Pool)==IntPtr.Zero,"Null context accepted");guards++;
            if(entries){
                Stage(directory,"checking bootstrap initialization gate");
                IntPtr descriptor=NativeLibrary.GetExport(image,"boom_concat_fixture_class");long live=Marshal.ReadInt64(heap,56);
                Marshal.WriteInt32(descriptor,8,0);Reset(ctx);Need(Call(concatenate,sample,ctx)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==20&&Marshal.ReadInt64(heap,56)==live,"Generated thunk bypassed required bootstrap initialization");guards++;
                Marshal.WriteInt32(descriptor,8,2);
                Stage(directory,"bootstrap gate verified");
            }
            Marshal.Copy(metadata,0,bad,80);IntPtr emptyHeapCell=Memory(memory,8);Marshal.WriteIntPtr(bad,24,emptyHeapCell);Reset(ctx);Need(concatenate(ctx,sample.Args,bad)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==20,"Unbound concat heap accepted");guards++;
            IntPtr roots=Memory(memory,(inputs.Count+1)*8);Marshal.WriteIntPtr(roots,last);for(int i=0;i<inputs.Count;i++)Marshal.WriteIntPtr(roots,(i+1)*8,inputs[i]);
            Stage(directory,"collecting source graph");long garbage=GC(collect,heap,spans,roots,inputs.Count+1);Need(garbage>cases.Count&&Text(last,source)==cases[cases.Count-1].Expected,"Concat collection lost live source objects");
            long filled=0;while(allocate(heap,4096,0,264)!=IntPtr.Zero)filled++;while(allocate(heap,0,0,264)!=IntPtr.Zero)filled++;
            Stage(directory,"checking OOM");Reset(ctx);Need(Call(concatenate,sample,ctx)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==3,"Concat OOM returned a fake String");guards++;
            long afterOOM=GC(collect,heap,spans,roots,inputs.Count+1);Need(afterOOM>=filled,"Concat OOM garbage retained");Reset(ctx);IntPtr retry=Call(concatenate,sample,ctx);Need(Marshal.ReadInt32(ctx)==0&&Text(retry,source)==sample.Expected,"Concat retry failed");
            var result=new long[]{cases.Count,workers*iterations,guards,garbage,afterOOM,inputs.Count,Marshal.ReadInt64(heap,56)};
            Need(destroy(heap)==1,"Concat heap cleanup failed");heap=IntPtr.Zero;return result;
        }finally{if(heap!=IntPtr.Zero)destroy(heap);for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(image!=IntPtr.Zero)NativeLibrary.Free(image);NativeLibrary.Free(lib);}
    }
}
