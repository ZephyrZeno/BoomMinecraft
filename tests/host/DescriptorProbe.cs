// Development orchestration only: descriptor initialization, workers and IO are MASM.
using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomDescriptorProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int n);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFileW(string p,uint access,uint share,IntPtr security,uint disposition,uint flags,IntPtr template);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern bool SetFilePointerEx(IntPtr h,long offset,out long position,uint method);
    [DllImport("kernel32.dll")] static extern bool CreatePipe(out IntPtr read,out IntPtr write,IntPtr security,uint size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr GetPool();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Class(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint n,uint f);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(ref Context c,[In] ulong[] a,IntPtr p,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr h,int n,uint kind,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static void Check(bool ok,string s){if(!ok)throw new Exception(s);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Descriptor probe DLL load failed");return m;}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static IntPtr Array(IntPtr r,IntPtr h,int n){var c=new Context();IntPtr a=Fn<ArrayNew>(r,"boom_array_new")(h,n,8,ref c);Check(a!=IntPtr.Zero&&c.Kind==0,"IO byte array allocation failed");return a;}
    static ulong Call(Service f,IntPtr p,uint op,ulong[] a,uint kind){var c=new Context();ulong v=f(ref c,a,p,op);Check(c.Kind==kind&&c.Depth==0,"Descriptor service error category changed: op="+op+", expected="+kind+", actual="+c.Kind);return v;}
    static void Metadata(Service f,IntPtr source){
        IntPtr p=Marshal.AllocHGlobal(32),t=Marshal.AllocHGlobal(48);try{
            long[] pool=new long[4],table=new long[6];Marshal.Copy(source,pool,0,4);Marshal.Copy(Marshal.ReadIntPtr(source,8),table,0,6);Marshal.Copy(table,0,t,6);pool[1]=t.ToInt64();pool[2]=0;Marshal.Copy(pool,0,p,4);
            Call(f,p,1,new ulong[]{0},20);Call(f,p,0,new ulong[0],0);Check(Marshal.ReadIntPtr(p,16)==t,"Native field table was not published");Call(f,p,0,new ulong[0],0);
            foreach(int offset in new int[]{0,4,20,24,28,36,40}){long saved=Marshal.ReadInt64(t,offset);Marshal.WriteInt64(t,offset,3);Call(f,p,0,new ulong[0],7);Marshal.WriteInt64(t,offset,saved);}
            Marshal.WriteIntPtr(p,16,new IntPtr(1));Call(f,p,1,new ulong[]{0},7);Marshal.WriteIntPtr(p,16,t);
            Call(f,p,999,new ulong[0],7);var c=new Context{Kind=3,PC=19,Method=71,Depth=2};f(ref c,new ulong[0],IntPtr.Zero,999);Check(c.Kind==3&&c.PC==19&&c.Method==71&&c.Depth==2,"Native IO overwrote a pending error");
        }finally{Marshal.FreeHGlobal(t);Marshal.FreeHGlobal(p);}
    }
    static IntPtr Object(IntPtr m,uint owner,uint field){IntPtr cell=Fn<Field>(m,"boom_get_static_field")(owner,field);Check(cell!=IntPtr.Zero,"Missing standard descriptor cell");return Marshal.ReadIntPtr(cell);}
    public static void Parallel(string dll,string runtime,uint owner,uint[] fields){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,workers=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Descriptor heap failed");
            IntPtr p=Fn<GetPool>(m,"boom_get_fd_pool")(),table=Marshal.ReadIntPtr(p,8),descriptor=Fn<Class>(m,"boom_get_class_descriptor")(owner);
            Check(Marshal.ReadInt32(descriptor,8)==0&&Marshal.ReadIntPtr(p,16)==IntPtr.Zero,"Descriptor initialized before first active use");
            var service=Fn<Service>(r,"boom_fd_service");Metadata(service,p);Call(service,p,1,new ulong[]{0},20);
            const int count=2049;long[] args=new long[count*16];for(int i=0;i<count;i++)args[i*16]=unchecked((uint)(0x80000000U+(uint)i*65537));
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);workers=Fn<PoolCreate>(r,"boom_pool_create")(8);
            Check(workers!=IntPtr.Zero,"Descriptor workers failed");
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(r,"boom_pool_run")(workers,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Descriptor batch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked((uint)args[i*16]+7)&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent descriptor initialization changed results");
                Check(Marshal.ReadInt32(descriptor,8)==2&&Marshal.ReadIntPtr(p,16)==table&&Marshal.ReadInt64(heap,56)==4,"Original descriptor initialization or native field publication changed");
                IntPtr[] objects=new IntPtr[3];int handleOffset=Marshal.ReadInt32(table,24),fdOffset=Marshal.ReadInt32(table,16),appendOffset=Marshal.ReadInt32(table,32);
                for(int i=0;i<3;i++){objects[i]=Object(m,owner,fields[i]);Check(objects[i]!=IntPtr.Zero&&Marshal.ReadInt32(objects[i],fdOffset)==i&&Marshal.ReadIntPtr(objects[i],handleOffset)==GetStdHandle(-10-i)&&Marshal.ReadByte(objects[i],appendOffset)==0,"Original descriptor fields differ from actual Windows handles");}
                Check(objects[0]!=objects[1]&&objects[1]!=objects[2]&&objects[0]!=objects[2],"Standard descriptor identities merged");
                IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)==0&&Marshal.ReadInt64(heap,56)==4,"Descriptor static graph was lost or leaked");
            }
            foreach(uint fd in new uint[]{0,1,2,3,0xffffffff,0x80000000}){
                ulong h=Call(service,p,1,new ulong[]{fd},0);Check(h==(fd<3?Bits(GetStdHandle(-10-(int)fd)):ulong.MaxValue),"Standard handle selection changed");
                Check(Call(service,p,2,new ulong[]{fd},0)==0,"Windows descriptor append default changed");
            }
        }finally{if(workers!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(workers);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
    static void Same(byte[] a,byte[] b){Check(a.Length==b.Length,"IO byte count changed");for(int i=0;i<a.Length;i++)Check(a[i]==b[i],"IO bytes changed at "+i);}
    static HashSet<string> Records(byte[] a){Check(a.Length==6147*16,"Append file length changed");var set=new HashSet<string>();for(int i=0;i<a.Length;i+=16){int id=BitConverter.ToInt32(a,i),batch=BitConverter.ToInt32(a,i+4);Check(id>=0&&id<2049&&batch>=0&&batch<3&&BitConverter.ToInt32(a,i+8)==0x12345678&&BitConverter.ToInt32(a,i+12)==(id^batch^0x13579bdf),"Concurrent append record was torn");Check(set.Add(id+":"+batch),"Concurrent append record repeated");}return set;}
    public static void Io(string dll,string runtime,string worker,uint owner,uint outputField,string directory){
        IntPtr m=Open(dll),r=Open(runtime),w=Open(worker),heap=IntPtr.Zero,h=IntPtr.Zero,append=IntPtr.Zero,workers=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(m,"boom_heap_create")(8*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"IO heap failed");var c=new Context();Check(Fn<Entry>(m,"boom_entry")(ref c,new ulong[]{0})==7&&c.Kind==0,"IO descriptor bootstrap failed");
            IntPtr p=Fn<GetPool>(m,"boom_get_fd_pool")(),table=Marshal.ReadIntPtr(p,8),fd=Object(m,owner,outputField);int handleOffset=Marshal.ReadInt32(table,24);var service=Fn<Service>(r,"boom_fd_service");
            string file=Path.Combine(directory,"native 汇编 bytes.bin"),app=Path.Combine(directory,"native append.bin");
            h=CreateFileW(file,0xc0000000,3,IntPtr.Zero,2,0x80,IntPtr.Zero);Check(h!=new IntPtr(-1),"Owned IO file creation failed");Marshal.WriteIntPtr(fd,handleOffset,h);
            byte[] expected=File.ReadAllBytes(Path.Combine(directory,"jvm-bytes.bin")),inputBytes=new byte[expected.Length+32];for(int i=0;i<inputBytes.Length;i++)inputBytes[i]=0x5a;System.Array.Copy(expected,0,inputBytes,7,expected.Length);
            IntPtr bytes=Array(r,heap,inputBytes.Length),read=Array(r,heap,inputBytes.Length);Marshal.Copy(inputBytes,0,bytes,inputBytes.Length);
            Call(service,p,3,new ulong[]{Bits(fd),Bits(bytes),7,(ulong)expected.Length,0},0);Call(service,p,5,new ulong[]{Bits(fd)},0);
            Check(SetFilePointerEx(h,0,out long pos,0)&&pos==0,"Owned IO seek failed");
            ulong got=Call(service,p,4,new ulong[]{Bits(fd),Bits(read),11,(ulong)expected.Length},0);Check(got==(ulong)expected.Length,"Read did not return requested bytes");byte[] actual=new byte[expected.Length];Marshal.Copy(IntPtr.Add(read,11),actual,0,actual.Length);Same(expected,actual);
            Check(Call(service,p,4,new ulong[]{Bits(fd),Bits(read),0,1},0)==uint.MaxValue,"File EOF changed");
            Call(service,p,3,new ulong[]{Bits(fd),0,0,0,0},4);Call(service,p,4,new ulong[]{Bits(fd),Bits(read),0xffffffff,0},5);
            Call(service,p,3,new ulong[]{Bits(fd),Bits(bytes),(ulong)inputBytes.Length,1,0},5);Call(service,p,4,new ulong[]{0,Bits(read),0,0},0);
            Marshal.WriteIntPtr(fd,handleOffset,new IntPtr(-1));Call(service,p,3,new ulong[]{Bits(fd),Bits(bytes),0,1,0},21);Call(service,p,4,new ulong[]{Bits(fd),Bits(read),0,1},21);Call(service,p,5,new ulong[]{Bits(fd)},22);Marshal.WriteIntPtr(fd,handleOffset,h);
            Check(CreatePipe(out IntPtr pipeRead,out IntPtr pipeWrite,IntPtr.Zero,0),"Owned EOF pipe creation failed");try{Check(CloseHandle(pipeWrite),"Owned pipe writer close failed");pipeWrite=IntPtr.Zero;Marshal.WriteIntPtr(fd,handleOffset,pipeRead);Check(Call(service,p,4,new ulong[]{Bits(fd),Bits(read),0,1},0)==uint.MaxValue,"Broken pipe EOF changed");}finally{if(pipeWrite!=IntPtr.Zero)CloseHandle(pipeWrite);CloseHandle(pipeRead);Marshal.WriteIntPtr(fd,handleOffset,h);}
            Check(CloseHandle(h),"Owned byte file close failed");h=IntPtr.Zero;
            Same(expected,File.ReadAllBytes(file));byte[] still=new byte[inputBytes.Length];Marshal.Copy(bytes,still,0,still.Length);Same(inputBytes,still);
            append=CreateFileW(app,0xc0000000,3,IntPtr.Zero,2,0x80,IntPtr.Zero);Check(append!=new IntPtr(-1),"Owned append file creation failed");Marshal.WriteIntPtr(fd,handleOffset,append);
            const int count=2049;long[] args=new long[count*16];IntPtr[] records=new IntPtr[count];
            for(int i=0;i<count;i++){records[i]=Array(r,heap,16);args[i*16]=unchecked((long)Bits(fd));args[i*16+1]=unchecked((long)Bits(records[i]));args[i*16+3]=16;args[i*16+4]=1;args[i*16+5]=unchecked((long)Bits(p));}
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);workers=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(workers!=IntPtr.Zero,"IO workers failed");long live=Marshal.ReadInt64(heap,56);
            for(int batch=0;batch<3;batch++){
                for(int i=0;i<count;i++){Marshal.WriteInt32(records[i],0,i);Marshal.WriteInt32(records[i],4,batch);Marshal.WriteInt32(records[i],8,0x12345678);Marshal.WriteInt32(records[i],12,i^batch^0x13579bdf);}
                Check(Fn<PoolRun>(r,"boom_pool_run")(workers,GetProcAddress(w,"boom_entry"),input,output,count)==0,"Concurrent append dispatch failed");
                for(int i=0;i<count;i++)for(int q=0;q<4;q++)Check(Marshal.ReadInt64(output,i*32+q*8)==0,"Concurrent append context changed");
                Check(Marshal.ReadInt64(heap,56)==live,"Native file IO allocated guest temporaries");
            }
            Call(service,p,5,new ulong[]{Bits(fd)},0);Check(CloseHandle(append),"Owned append file close failed");append=IntPtr.Zero;
            var referenceRecords=Records(File.ReadAllBytes(Path.Combine(directory,"jvm-append.bin")));Check(referenceRecords.SetEquals(Records(File.ReadAllBytes(app))),"Native append differs from JVM reference records");
            IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)==(ulong)count+2&&Marshal.ReadInt64(heap,56)==4,"IO fixture temporaries or descriptor roots leaked");
        }finally{if(workers!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(workers);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(append!=IntPtr.Zero&&append!=new IntPtr(-1))CloseHandle(append);if(h!=IntPtr.Zero&&h!=new IntPtr(-1))CloseHandle(h);if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(w);FreeLibrary(r);FreeLibrary(m);}
    }
}
