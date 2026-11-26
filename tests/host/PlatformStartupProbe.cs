// Development controller. Windows signal/error-mode services and callbacks run ASM.
// Signal callbacks here are explicit VM fixtures, not original Signal.dispatch.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
public static class BoomPlatformStartupProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;public ulong Pending,VM;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll")] static extern uint GetErrorMode();
    [DllImport("kernel32.dll")] static extern uint SetErrorMode(uint mode);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr CreateEventW(IntPtr security,bool manual,bool initial,string name);
    [DllImport("kernel32.dll")] static extern bool SetEvent(IntPtr h);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h,uint ms);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(IntPtr config);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Bind(IntPtr control,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Query(ref Context c,[In] ulong[] args,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Snapshot(IntPtr control,IntPtr output);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void AdapterBind(IntPtr user);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapOne(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    static void Check(bool v,string s){if(!v)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string name){IntPtr p=GetProcAddress(m,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Module load failed: "+p);return m;}
    static IntPtr Block(int n){IntPtr p=Marshal.AllocHGlobal(n);Marshal.Copy(new byte[n],0,p,n);return p;}
    static long BE64(BinaryReader b){byte[] v=b.ReadBytes(8);Check(v.Length==8,"Truncated oracle");if(BitConverter.IsLittleEndian)Array.Reverse(v);return BitConverter.ToInt64(v,0);}
    static int BE32(BinaryReader b){byte[] v=b.ReadBytes(4);Check(v.Length==4,"Truncated oracle");if(BitConverter.IsLittleEndian)Array.Reverse(v);return BitConverter.ToInt32(v,0);}
    static long Call(Query query,IntPtr pool,uint op,int signal,long value=0){var c=new Context();ulong result=query(ref c,new[]{unchecked((ulong)signal),unchecked((ulong)value)},pool,op);Check(c.Kind==0,"Signal native failed: "+c.Kind);return unchecked((long)result);}
    static void Until(Func<bool> f,string message){long deadline=Environment.TickCount64+15000;while(!f()){Check(Environment.TickCount64<deadline,message);Thread.Sleep(1);}}
    public static void Signals(string runtime,string adapter,string oracle){
        IntPtr r=Open(runtime),a=Open(adapter),pool=Block(64),trace=Block(48),config=Block(48),user=Block(256),stats=Block(64),control=IntPtr.Zero,entered=IntPtr.Zero,release=IntPtr.Zero;
        var close=Fn<One>(r,"boom_signal_control_close");var bind=Fn<Bind>(r,"boom_signal_native_bind");var query=Fn<Query>(r,"boom_signal_native_query");var snapshot=Fn<Snapshot>(r,"boom_signal_control_snapshot");
        try{
            Marshal.WriteInt32(pool,0x504e4753);Marshal.WriteInt32(pool,4,1);Marshal.WriteIntPtr(pool,32,trace);Marshal.WriteInt32(trace,0x5452504c);Marshal.WriteInt32(trace,4,2);Marshal.WriteInt32(trace,12,-1);
            var unbound=new Context();Check(query(ref unbound,new ulong[]{2,2},pool,0)==0&&unbound.Kind==7,"Unbound signal bridge silently succeeded");
            Check(bind(new IntPtr(1),pool)==87,"Foreign transport accepted");
            Marshal.WriteInt32(config,0x53474346);Marshal.WriteInt32(config,4,1);Marshal.WriteIntPtr(config,8,GetProcAddress(a,"boom_signal_test_dispatch"));Marshal.WriteIntPtr(config,16,GetProcAddress(a,"boom_signal_test_break"));Marshal.WriteIntPtr(config,24,user);
            control=Fn<Create>(r,"boom_signal_control_create")(config);Check(control!=IntPtr.Zero&&bind(control,pool)==0&&bind(control,pool)==0,"Live transport bind failed");
            Check(bind(IntPtr.Zero,pool)==170,"Live transport unbound before close/join");
            for(int offset=0;offset<64;offset+=8){if(offset==8||offset==16||offset==24)continue;long saved=Marshal.ReadInt64(pool,offset);Marshal.WriteInt64(pool,offset,offset==32?0:7);Check(bind(control,pool)==87,"Malformed native pool accepted");Marshal.WriteInt64(pool,offset,saved);}
            Marshal.WriteInt64(trace,32,1);Check(bind(control,pool)==170,"Binding changed with active Java frames");Marshal.WriteInt64(trace,32,0);
            var pending=new Context{Kind=19,PC=31,Method=17,Depth=2,Pending=0xabc,VM=0xdef};Check(query(ref pending,new ulong[]{2,0},pool,0)==0&&pending.Kind==19&&pending.PC==31&&pending.Method==17&&pending.Depth==2&&pending.Pending==0xabc&&pending.VM==0xdef,"Pending context changed");
            using(var b=new BinaryReader(File.OpenRead(oracle))){for(int i=0;i<4096;i++){int number=BE32(b);long value=BE64(b),expected=BE64(b);Check(Call(query,pool,0,number,value)==expected,"JVM registration result differs at "+i);}Check(b.BaseStream.Position==b.BaseStream.Length,"Trailing registration oracle");}
            foreach(int number in new[]{-1,0,3,23,int.MaxValue}){Check(Call(query,pool,0,number,2)==-1,"Invalid signal registration accepted");Call(query,pool,1,number);}
            Check(Call(query,pool,0,8,2)==-1&&Call(query,pool,0,21,2)==-1,"VM-owned signal accepted");
            Call(query,pool,0,2,2);uint caller=GetCurrentThreadId();Call(query,pool,1,2);
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==1,"Signal dispatch did not complete");Check(unchecked((uint)Marshal.ReadInt32(user,204))!=caller,"Java-style signal dispatched synchronously");
            Parallel.For(0,8,new ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int i=0;i<257;i++)Call(query,pool,1,2);});
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==2057,"Concurrent signal queue lost an event");Check(Marshal.ReadInt64(user,16)==2057&&Marshal.ReadInt64(user,192)==0&&Marshal.ReadInt64(pool,16)==0,"Signal callback/count/lease mismatch");
            entered=CreateEventW(IntPtr.Zero,true,false,null);release=CreateEventW(IntPtr.Zero,true,false,null);Check(entered!=IntPtr.Zero&&release!=IntPtr.Zero,"Native gate creation failed");Marshal.WriteIntPtr(user,208,entered);Marshal.WriteIntPtr(user,216,release);Marshal.WriteIntPtr(user,232,control);Marshal.WriteInt32(user,240,4);Fn<AdapterBind>(a,"boom_signal_test_bind")(user);
            Call(query,pool,0,15,GetProcAddress(a,"boom_signal_test_native").ToInt64());var active=Task.Run(()=>Call(query,pool,1,15));Check(WaitForSingleObject(entered,15000)==0,"Native callback did not enter");Check(Marshal.ReadInt64(pool,16)==1&&bind(control,pool)==170,"In-flight native callback did not retain binding lease");Check(SetEvent(release)&&active.Wait(15000),"Native callback did not return");Check(Marshal.ReadInt64(pool,16)==0&&Marshal.ReadInt64(user,224)==1,"Native callback lease leaked");
            Marshal.WriteIntPtr(user,208,IntPtr.Zero);Marshal.WriteIntPtr(user,216,IntPtr.Zero);Marshal.WriteInt32(user,240,0);
            Check(close(control)==0,"Signal transport close/join failed");control=IntPtr.Zero;
            var closed=new Context();Check(query(ref closed,new ulong[]{2,2},pool,0)==0&&closed.Kind==7,"Closed transport accepted");Check(bind(IntPtr.Zero,pool)==0&&Marshal.ReadIntPtr(pool,8)==IntPtr.Zero,"Closed transport did not unbind");
        }finally{if(release!=IntPtr.Zero)SetEvent(release);if(control!=IntPtr.Zero){close(control);bind(IntPtr.Zero,pool);}if(entered!=IntPtr.Zero)CloseHandle(entered);if(release!=IntPtr.Zero)CloseHandle(release);foreach(IntPtr p in new[]{pool,trace,config,user,stats})Marshal.FreeHGlobal(p);FreeLibrary(a);FreeLibrary(r);}
    }
    public static void ErrorMode(string image,string runtime,string oracle){
        IntPtr m=Open(image),r=Open(runtime),heap=IntPtr.Zero;uint saved=GetErrorMode();
        try{
            heap=Fn<HeapCreate>(m,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<HeapOne>(m,"boom_bind_heap")(heap)==1,"Error-mode heap bind failed");var entry=Fn<Entry>(m,"boom_entry");SetErrorMode(1);
            using(var b=new BinaryReader(File.OpenRead(oracle))){for(int i=0;i<256;i++){long mode=BE64(b),expected=BE64(b);uint previous=GetErrorMode();var c=new Context();ulong actual=entry(ref c,new[]{unchecked((ulong)mode)});Check(c.Kind==0&&actual==(ulong)previous&&actual==unchecked((ulong)expected),"Windows mode result differs at "+i);uint effective=GetErrorMode();uint directOld=SetErrorMode(unchecked((uint)mode));Check(directOld==effective&&GetErrorMode()==effective,"Mode input was not truncated to Windows UINT");}Check(b.BaseStream.Position==b.BaseStream.Length,"Trailing error-mode oracle");}
            uint before=GetErrorMode();var pending=new Context{Kind=7,PC=31,Method=17,Depth=2,Pending=0xabc,VM=0xdef};Check(Fn<Entry>(r,"boom_windows_error_mode")(ref pending,new[]{0UL})==0&&pending.Kind==7&&pending.PC==31&&pending.Method==17&&pending.Depth==2&&pending.Pending==0xabc&&pending.VM==0xdef&&GetErrorMode()==before,"Pending Windows native changed context/process mode");
        }finally{SetErrorMode(saved);if(heap!=IntPtr.Zero)Fn<HeapOne>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
}
