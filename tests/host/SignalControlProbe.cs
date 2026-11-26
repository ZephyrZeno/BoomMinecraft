// Native transport verification only. No managed callbacks run on its worker.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

public static class BoomSignalControlProbe {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr zero,uint flags);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CreateEventW(IntPtr security,bool manual,bool state,string name);
    [DllImport("kernel32.dll")] static extern bool SetEvent(IntPtr handle);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessW(string application,StringBuilder command,IntPtr processSecurity,IntPtr threadSecurity,bool inherit,uint flags,IntPtr environment,string directory,ref Startup startup,out Process process);
    [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr process,uint code);
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {
        public uint cb; public string reserved,desktop,title; public uint x,y,width,height,charsX,charsY,fill,flags;
        public ushort show,reservedBytes; public IntPtr reservedData,input,output,error;
    }
    [StructLayout(LayoutKind.Sequential)] struct Process {public IntPtr process,thread;public uint processId,threadId;}
    [UnmanagedFunctionPointer(CallingConvention.Cdecl,SetLastError=true)] delegate IntPtr Create(IntPtr config);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Close(IntPtr control);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Register(IntPtr control,int signal,long value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Raise(IntPtr control,int signal);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Snapshot(IntPtr control,IntPtr output);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint ConsoleEvent(uint number);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Bind(IntPtr user);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint ThreadSlots();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint workers);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr kernel,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolClose(IntPtr pool);
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string path){IntPtr m=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Module load: "+path);return m;}
    static IntPtr Zero(int bytes){IntPtr p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i+=8)Marshal.WriteInt64(p,i,0);return p;}
    static void Until(Func<bool> condition,string message){var limit=Environment.TickCount64+15000;while(!condition()){Check(Environment.TickCount64<limit,message);Thread.Sleep(1);}}
    static long Read64BE(BinaryReader r){byte[] b=r.ReadBytes(8);Check(b.Length==8,"Truncated signal oracle");if(BitConverter.IsLittleEndian)Array.Reverse(b);return BitConverter.ToInt64(b,0);}
    static int Read32BE(BinaryReader r){byte[] b=r.ReadBytes(4);Check(b.Length==4,"Truncated signal oracle");if(BitConverter.IsLittleEndian)Array.Reverse(b);return BitConverter.ToInt32(b,0);}
    static IntPtr Config(IntPtr adapter,IntPtr user){IntPtr p=Zero(48);Marshal.WriteInt32(p,0,0x53474346);Marshal.WriteInt32(p,4,1);Marshal.WriteIntPtr(p,8,GetProcAddress(adapter,"boom_signal_test_dispatch"));Marshal.WriteIntPtr(p,16,GetProcAddress(adapter,"boom_signal_test_break"));Marshal.WriteIntPtr(p,24,user);return p;}

    public static void Transport(string runtime,string adapter,string oracle,string localOracle){
        IntPtr r=Open(runtime),a=Open(adapter),user=Zero(256),config=Config(a,user),stats=Zero(64),control=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        var create=Fn<Create>(r,"boom_signal_control_create");var close=Fn<Close>(r,"boom_signal_control_close");var register=Fn<Register>(r,"boom_signal_control_register");var raise=Fn<Raise>(r,"boom_signal_control_raise");var snapshot=Fn<Snapshot>(r,"boom_signal_control_snapshot");
        long delivered=0;
        try {
            Check(create(IntPtr.Zero)==IntPtr.Zero,"Null signal config accepted");
            foreach(int offset in new[]{0,4,8,16,32,40}){
                long saved=Marshal.ReadInt64(config,offset);Marshal.WriteInt64(config,offset,offset<8?7:offset<24?0:1);
                Check(create(config)==IntPtr.Zero,"Malformed signal config accepted: "+offset);Marshal.WriteInt64(config,offset,saved);
            }
            control=create(config);Check(control!=IntPtr.Zero,"Signal transport create failed");
            Marshal.WriteIntPtr(user,232,control);Fn<Bind>(a,"boom_signal_test_bind")(user);
            Check(create(config)==IntPtr.Zero,"Two active process transports accepted");
            using(var b=new BinaryReader(File.OpenRead(oracle))){Check(b.BaseStream.Length==4096*20,"Signal registration oracle size changed");for(int i=0;i<4096;i++){int number=Read32BE(b);long value=Read64BE(b),expected=Read64BE(b);Check(register(control,number,value)==expected,"Signal registration differs from JVM: "+i);}}
            using(var b=new BinaryReader(File.OpenRead(localOracle))){
                Check(b.BaseStream.Length==88,"Thread-local signal oracle size differs");
                foreach(int number in new[]{4,11}){
                    register(control,number,0);Check(register(control,number,1)==Read64BE(b),"Main thread signal setup differs");
                    uint slots=Fn<ThreadSlots>(r,"boom_signal_control_thread_slots")();
                    var values=new long[2];var thread=new Thread(()=>{values[0]=register(control,number,2);values[1]=register(control,number,0);});thread.Start();Check(thread.Join(15000),"Local signal test thread did not exit");
                    Check(values[0]==Read64BE(b)&&values[1]==Read64BE(b)&&register(control,number,0)==Read64BE(b),"ILL/SEGV dispositions leaked across threads");
                    Until(()=>Fn<ThreadSlots>(r,"boom_signal_control_thread_slots")()==slots,"Exited thread signal storage was not freed");
                }
                register(control,22,0);Check(register(control,6,1)==Read64BE(b),"ABRT alias initial state differs");long aliasOld=-99;
                var aliasThread=new Thread(()=>aliasOld=register(control,22,2));aliasThread.Start();Check(aliasThread.Join(15000),"ABRT alias thread did not exit");
                Check(aliasOld==Read64BE(b)&&register(control,6,0)==Read64BE(b),"ABRT compatibility alias did not share process state");
            }
            foreach(int number in new[]{2,4,11,15,22})Check(register(control,number,2)>=0,"Signal handler reset failed");
            Check(register(control,8,2)==-1&&register(control,21,2)==-1,"VM-owned signals accepted");
            foreach(int number in new[]{-1,0,3,23,int.MaxValue})Check(register(control,number,2)==-1&&raise(control,number)==87,"Invalid signal accepted");
            Check(register(control,2,-1)==-1,"SIG_ERR accepted as a handler");
            Check(register(control,2,3)==-1&&register(control,2,4)==-1,"Unsupported CRT action codes accepted");
            uint caller=GetCurrentThreadId();Check(raise(control,2)==0,"Signal enqueue failed");delivered++;
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==delivered,"Signal callback did not run");
            Check(Marshal.ReadInt64(user,16)==1&&unchecked((uint)Marshal.ReadInt32(user,204))!=caller,"Signal callback ran synchronously/on caller");
            Check(raise(control,21)==0,"VM BREAK enqueue failed");delivered++;
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==delivered,"BREAK callback did not run");
            Check(Marshal.ReadInt64(user,184)==1,"VM BREAK used Java dispatch instead of VM callback");
            Check(raise(control,6)==0,"ABRT compatibility alias raise failed");delivered++;
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==delivered,"ABRT compatibility alias did not dispatch");Check(Marshal.ReadInt64(user,48)==1,"ABRT compatibility raise lost its original number");
            register(control,4,1);for(int i=0;i<64;i++)Check(raise(control,4)==0,"Ignored signal failed");
            Check(Marshal.ReadInt64(user,32)==0,"Ignored signal dispatched");
            Marshal.WriteInt32(user,200,15);Check(raise(control,15)==0,"Failing callback enqueue failed");delivered++;
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==delivered,"Failing callback did not run");
            Check(Marshal.ReadInt64(stats,8)==1&&Marshal.ReadInt32(stats,16)==12345,"Callback failure was not observable");Marshal.WriteInt32(user,200,0);
            var console=Fn<ConsoleEvent>(r,"boom_signal_control_console");Check(console(44)==0&&console(2)==1&&console(6)==1,"Console event routing failed");delivered+=2;
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==delivered,"TERM callback routing did not run");
            Check(Marshal.ReadInt64(stats,32)==2,"Direct console callback routing count differs");
            long native=GetProcAddress(a,"boom_signal_test_native").ToInt64();
            register(control,11,native);Check(raise(control,11)==0&&Marshal.ReadInt64(user,224)==1,"Native callback did not run");Check(register(control,11,2)==0,"Native callback was not reset before entry");
            Marshal.WriteInt32(user,240,1);register(control,11,native);Check(raise(control,11)==0&&register(control,11,2)==2,"Native callback could not reinstall a handler");
            Marshal.WriteInt32(user,240,2);register(control,11,native);Check(raise(control,11)==0&&Marshal.ReadInt32(user,244)==1131,"Native callback close deadlocked/was accepted");register(control,11,2);
            Marshal.WriteInt32(user,240,3);Check(raise(control,11)==0,"Worker close rejection enqueue failed");delivered++;
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==delivered,"Worker close rejection did not run");Check(Marshal.ReadInt32(user,248)==1131,"Worker closed its own transport");Marshal.WriteInt32(user,240,0);

            const int count=2049;pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Assembly pool create failed");input=Zero(count*128);output=Zero(count*32);
            for(int batch=0;batch<3;batch++){
                register(control,22,0);var histogram=new long[3];
                for(int i=0;i<count;i++){Marshal.WriteIntPtr(input,i*128,control);Marshal.WriteInt64(input,i*128+8,22);Marshal.WriteInt64(input,i*128+16,i%3);histogram[i%3]++;}
                Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(a,"boom_signal_test_register_job"),input,output,count)==0,"Assembly registration pool failed");
                var observed=new long[3];for(int i=0;i<count;i++){long previous=Marshal.ReadInt64(output,i*32);Check(previous>=0&&previous<=2&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent registration result/context differs");observed[previous]++;}
                long final=register(control,22,0);for(int value=0;value<3;value++)Check(observed[value]==histogram[value]+(value==0?1:0)-(value==final?1:0),"Registration updates were lost");
            }
            register(control,22,2);long before=Marshal.ReadInt64(user,176);
            for(int i=0;i<count;i++){Marshal.WriteIntPtr(input,i*128,control);Marshal.WriteInt64(input,i*128+8,22);}
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(a,"boom_signal_test_raise_job"),input,output,count)==0,"Assembly raise pool failed");
                for(int i=0;i<count;i++)Check(Marshal.ReadInt64(output,i*32)==0&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent raise failed");
            }
            delivered+=count*3;Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats)==delivered,"Queued multicore signals were lost");Check(Marshal.ReadInt64(user,176)==before+count*3,"Multicore callback count differs");
            Check(Fn<PoolClose>(r,"boom_pool_destroy")(pool)==0,"Assembly signal workers did not join");pool=IntPtr.Zero;
            Check(Marshal.ReadInt64(user,192)==0,"Signal worker leaked floating point state");

            IntPtr entered=CreateEventW(IntPtr.Zero,true,false,null),release=CreateEventW(IntPtr.Zero,true,false,null);
            Check(entered!=IntPtr.Zero&&release!=IntPtr.Zero,"Close barrier events failed");
            try {
                Marshal.WriteIntPtr(user,208,entered);Marshal.WriteIntPtr(user,216,release);before=Marshal.ReadInt64(user,176);
                Check(raise(control,22)==0&&WaitForSingleObject(entered,10000)==0,"Close barrier callback did not enter");
                for(int i=0;i<128;i++)Check(raise(control,22)==0,"Pending close drain enqueue failed");
                IntPtr closing=control;var task=Task.Run(()=>close(closing));
                Until(()=>snapshot(closing,stats)==87,"Transport did not detach before joining");Check(!task.IsCompleted,"Close freed a running callback");Check(create(config)==IntPtr.Zero,"New VM overlapped an unfinished close");
                Check(SetEvent(release),"Release callback barrier failed");Check(task.Wait(15000)&&task.Result==0,"Close failed to drain and join");control=IntPtr.Zero;
                Check(Marshal.ReadInt64(user,176)==before+129,"Close dropped accepted queued signals");
                Check(register(closing,4,2)==-1&&raise(closing,4)==87&&snapshot(closing,stats)==87&&close(closing)==87,"Detached transport accepted operations");
            } finally {SetEvent(release);CloseHandle(entered);CloseHandle(release);Marshal.WriteIntPtr(user,208,IntPtr.Zero);Marshal.WriteIntPtr(user,216,IntPtr.Zero);}
            for(int i=0;i<16;i++){control=create(config);Check(control!=IntPtr.Zero&&register(control,4,0)==0&&register(control,4,1)==0&&close(control)==0,"Repeated signal lifecycle/generation reset failed");control=IntPtr.Zero;}
            var creators=new Task<IntPtr>[8];for(int i=0;i<creators.Length;i++)creators[i]=Task.Run(()=>create(config));Task.WaitAll(creators);
            int winners=0;foreach(var task in creators)if(task.Result!=IntPtr.Zero){control=task.Result;winners++;}
            Check(winners==1,"Concurrent create did not produce exactly one VM transport");Check(close(control)==0,"Concurrent create cleanup failed");control=IntPtr.Zero;
            control=create(config);Check(control!=IntPtr.Zero,"Native operation barrier setup failed");Marshal.WriteIntPtr(user,232,control);
            entered=CreateEventW(IntPtr.Zero,true,false,null);release=CreateEventW(IntPtr.Zero,true,false,null);Check(entered!=IntPtr.Zero&&release!=IntPtr.Zero,"Native operation barrier events failed");
            try {
                Marshal.WriteInt32(user,240,4);Marshal.WriteIntPtr(user,208,entered);Marshal.WriteIntPtr(user,216,release);register(control,11,native);
                IntPtr closing=control;var operation=Task.Run(()=>{register(closing,11,native);return raise(closing,11);});Check(WaitForSingleObject(entered,10000)==0,"Native handler operation did not enter");
                var task=Task.Run(()=>close(closing));Until(()=>snapshot(closing,stats)==87,"Native operation close did not detach");Check(!task.IsCompleted,"Close freed an active native operation");Check(create(config)==IntPtr.Zero,"New VM overlapped an active native operation close");
                SetEvent(release);Check(operation.Wait(15000)&&operation.Result==0&&task.Wait(15000)&&task.Result==0,"Native operation lease did not join safely");control=IntPtr.Zero;
            } finally {SetEvent(release);CloseHandle(entered);CloseHandle(release);Marshal.WriteIntPtr(user,208,IntPtr.Zero);Marshal.WriteIntPtr(user,216,IntPtr.Zero);Marshal.WriteInt32(user,240,0);}
        } finally {
            if(pool!=IntPtr.Zero)Fn<PoolClose>(r,"boom_pool_destroy")(pool);
            if(control!=IntPtr.Zero)close(control);
            foreach(IntPtr p in new[]{user,config,stats,input,output})if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);
            FreeLibrary(a);FreeLibrary(r);
        }
    }
    public static void Lifecycle(string runtime,string adapter){
        IntPtr r=Open(runtime),a=Open(adapter),user=Zero(320),config=Zero(64),stats=Zero(64),control=IntPtr.Zero;
        var create=Fn<Create>(r,"boom_signal_control_create");var close=Fn<Close>(r,"boom_signal_control_close");
        var register=Fn<Register>(r,"boom_signal_control_register");var raise=Fn<Raise>(r,"boom_signal_control_raise");var snapshot=Fn<Snapshot>(r,"boom_signal_control_snapshot");
        Marshal.WriteInt32(config,0,0x53474346);Marshal.WriteInt32(config,4,2);
        Marshal.WriteIntPtr(config,8,GetProcAddress(a,"boom_signal_test_lifecycle_dispatch"));
        Marshal.WriteIntPtr(config,16,GetProcAddress(a,"boom_signal_test_break"));Marshal.WriteIntPtr(config,24,user);
        Marshal.WriteIntPtr(config,48,GetProcAddress(a,"boom_signal_test_enter"));Marshal.WriteIntPtr(config,56,GetProcAddress(a,"boom_signal_test_exit"));
        try {
            foreach(int offset in new[]{48,56}){
                IntPtr saved=Marshal.ReadIntPtr(config,offset);Marshal.WriteIntPtr(config,offset,IntPtr.Zero);
                Check(create(config)==IntPtr.Zero&&Marshal.GetLastWin32Error()==87,"Missing lifecycle hook accepted");Marshal.WriteIntPtr(config,offset,saved);
            }
            Marshal.WriteInt32(user,280,12346);
            Check(create(config)==IntPtr.Zero&&Marshal.GetLastWin32Error()==12346,"Failed enter was published or its error changed");
            Check(Marshal.ReadInt64(user,256)==1&&Marshal.ReadInt64(user,264)==0&&Marshal.ReadInt64(user,304)==0,"Failed enter called exit or remained active");
            for(int i=0;i<320;i+=8)Marshal.WriteInt64(user,i,0);
            IntPtr entered=CreateEventW(IntPtr.Zero,true,false,null),release=CreateEventW(IntPtr.Zero,true,false,null);
            Check(entered!=IntPtr.Zero&&release!=IntPtr.Zero,"Lifecycle enter gates failed");Task<IntPtr> creating=null;
            try {
                Marshal.WriteIntPtr(user,288,entered);Marshal.WriteIntPtr(user,296,release);
                creating=Task.Run(()=>create(config));Check(WaitForSingleObject(entered,10000)==0,"Worker enter did not run");
                Check(!creating.IsCompleted,"Create published before worker enter returned");
                Check(SetEvent(release)&&creating.Wait(15000),"Worker enter barrier did not complete");control=creating.Result;
                Check(control!=IntPtr.Zero&&Marshal.ReadInt64(user,256)==1&&Marshal.ReadInt64(user,304)==1,"Successful enter was not committed");
            } finally {
                SetEvent(release);
                if(creating!=null){Check(creating.Wait(25000),"Creating worker did not leave the test gate");if(control==IntPtr.Zero)control=creating.Result;}
                Marshal.WriteIntPtr(user,288,IntPtr.Zero);Marshal.WriteIntPtr(user,296,IntPtr.Zero);CloseHandle(entered);CloseHandle(release);
            }
            uint tid=(uint)Marshal.ReadInt32(user,272);Check(tid!=0&&tid!=GetCurrentThreadId(),"Enter did not use the dispatcher OS thread");
            Check(register(control,22,2)==0&&raise(control,22)==0,"Lifecycle dispatch enqueue failed");
            Until(()=>snapshot(control,stats)==0&&Marshal.ReadInt64(stats,0)==1,"Lifecycle dispatch did not complete");
            Check(Marshal.ReadInt64(user,176)==1&&(uint)Marshal.ReadInt32(user,204)==tid&&Marshal.ReadInt64(stats,8)==0,"Dispatch ran outside the entered worker");
            entered=CreateEventW(IntPtr.Zero,true,false,null);release=CreateEventW(IntPtr.Zero,true,false,null);Check(entered!=IntPtr.Zero&&release!=IntPtr.Zero,"Lifecycle exit gates failed");Task<uint> closing=null;
            try {
                Marshal.WriteIntPtr(user,288,entered);Marshal.WriteIntPtr(user,296,release);IntPtr owned=control;closing=Task.Run(()=>close(owned));
                Check(WaitForSingleObject(entered,10000)==0,"Worker exit did not run");Check(!closing.IsCompleted,"Close returned before worker exit completed");
                Check(Marshal.ReadInt64(user,264)==1&&Marshal.ReadInt64(user,304)==1,"Exit barrier did not retain worker lifetime");
                Check(SetEvent(release)&&closing.Wait(15000)&&closing.Result==0,"Close failed to join successful worker exit");control=IntPtr.Zero;
            } finally {
                SetEvent(release);if(closing!=null){Check(closing.Wait(25000),"Closing worker did not leave test gate");control=IntPtr.Zero;}
                Marshal.WriteIntPtr(user,288,IntPtr.Zero);Marshal.WriteIntPtr(user,296,IntPtr.Zero);CloseHandle(entered);CloseHandle(release);
            }
            Check((uint)Marshal.ReadInt32(user,276)==tid&&Marshal.ReadInt64(user,304)==0&&Marshal.ReadInt64(user,192)==0,"Exit identity, active state or FP environment differs");
            Marshal.WriteInt32(user,284,12347);control=create(config);Check(control!=IntPtr.Zero,"Exit failure setup failed");
            uint exitFailure=close(control);control=IntPtr.Zero;Check(exitFailure==12347,"Worker exit failure was hidden");Marshal.WriteInt32(user,284,0);
            for(int i=0;i<8;i++){control=create(config);Check(control!=IntPtr.Zero&&close(control)==0,"Repeated lifecycle failed");control=IntPtr.Zero;}
            Check(Marshal.ReadInt64(user,256)==10&&Marshal.ReadInt64(user,264)==10&&Marshal.ReadInt64(user,304)==0,"Lifecycle hooks were lost or duplicated");
        } finally {
            if(control!=IntPtr.Zero)close(control);Marshal.FreeHGlobal(user);Marshal.FreeHGlobal(config);Marshal.FreeHGlobal(stats);FreeLibrary(a);FreeLibrary(r);
        }
    }
    public static void NativeChildren(string directory){
        RunHidden(Path.Combine(directory,"signal-console.exe"),0);
        foreach(int number in new[]{2,4,6,8,11,15,22})RunHidden(Path.Combine(directory,"signal-default-"+number+".exe"),3);
    }
    static void RunHidden(string path,uint expected){
        var startup=new Startup{cb=(uint)Marshal.SizeOf<Startup>(),flags=1,show=0};Process process;
        Check(CreateProcessW(path,new StringBuilder("\""+path+"\""),IntPtr.Zero,IntPtr.Zero,false,0x10,IntPtr.Zero,Path.GetDirectoryName(path),ref startup,out process),"Isolated console process failed: "+Marshal.GetLastWin32Error());
        bool ended=false;try{ended=WaitForSingleObject(process.process,30000)==0;Check(ended,"Isolated signal test timed out");Check(GetExitCodeProcess(process.process,out uint code)&&code==expected,"Isolated signal test returned "+code+", expected "+expected+": "+Path.GetFileName(path));}
        finally{if(!ended){TerminateProcess(process.process,99);WaitForSingleObject(process.process,5000);}CloseHandle(process.thread);CloseHandle(process.process);}
    }
}
