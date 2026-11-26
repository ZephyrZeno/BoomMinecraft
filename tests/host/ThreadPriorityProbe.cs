// Assembly registry kernel verification only; no Java Thread body is replaced.
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

public static class BoomThreadPriorityProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentThread();
    [DllImport("kernel32.dll")] static extern int GetThreadPriority(IntPtr h);
    [DllImport("kernel32.dll")] static extern bool SetThreadPriority(IntPtr h,int p);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll")] static extern IntPtr OpenThread(uint access,bool inherit,uint id);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr CreateEventW(IntPtr s,bool manual,bool state,string name);
    [DllImport("kernel32.dll")] static extern bool SetEvent(IntPtr e);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h,uint ms);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Allocate(IntPtr h,ulong n,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(IntPtr h,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint End(IntPtr r);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Next(IntPtr r);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Attach(IntPtr r,IntPtr o,ulong id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Start(IntPtr r,IntPtr c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Join(IntPtr r,IntPtr t,uint ms);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release(IntPtr r,IntPtr t);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Result(IntPtr r,IntPtr t,IntPtr output);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Priority(IntPtr r,IntPtr o,int p);
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Load failed "+p);return m;}
    static IntPtr Zero(int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i+=8)Marshal.WriteInt64(p,i,0);return p;}
    public static void Run(string runtime,string adapter){
        IntPtr m=Open(runtime),a=Open(adapter),heap=IntPtr.Zero,r=IntPtr.Zero,token=IntPtr.Zero,config=Zero(64),user=Zero(16),output=Zero(64);
        IntPtr entered=CreateEventW(IntPtr.Zero,true,false,null),gate=CreateEventW(IntPtr.Zero,true,false,null);
        var done=new ManualResetEventSlim(false);var ready=new ManualResetEventSlim(false);Thread external=null;Exception failure=null;uint externalIdOS=0;IntPtr query=IntPtr.Zero;Task<bool>[] racers=null;
        var end=Fn<End>(m,"boom_threads_destroy");var detach=Fn<End>(m,"boom_threads_detach");var priority=Fn<Priority>(m,"boom_threads_set_priority");
        var join=Fn<Join>(m,"boom_threads_join");var release=Fn<Release>(m,"boom_threads_release");var next=Fn<Next>(m,"boom_threads_next_id");
        int[] expected={-2,-2,-1,-1,0,0,1,1,2,2};
        try {
            heap=Fn<HeapCreate>(m,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero,"Heap failed");r=Fn<Create>(m,"boom_threads_create")(heap,32);Check(r!=IntPtr.Zero,"Registry failed");
            var alloc=Fn<Allocate>(m,"boom_heap_alloc");IntPtr root=alloc(heap,16,0,265),other=alloc(heap,16,0,265);Check(root!=IntPtr.Zero&&other!=IntPtr.Zero,"Roots failed");
            Check(priority(IntPtr.Zero,root,5)==87&&priority(r,IntPtr.Zero,5)==87,"Malformed identity accepted");
            foreach(int p in new[]{-1,0,11,int.MaxValue})Check(priority(r,root,p)==87,"Invalid Java priority accepted");
            Check(priority(r,root,10)==0,"NEW thread required an OS peer");Check(entered!=IntPtr.Zero&&gate!=IntPtr.Zero,"Events failed");
            Marshal.WriteIntPtr(user,0,entered);Marshal.WriteIntPtr(user,8,gate);
            Marshal.WriteInt32(config,0,0x5453504e);Marshal.WriteInt32(config,4,1);Marshal.WriteIntPtr(config,8,root);Marshal.WriteInt64(config,16,(long)next(r));
            Marshal.WriteIntPtr(config,24,GetProcAddress(a,"boom_priority_test_main"));Marshal.WriteIntPtr(config,32,GetProcAddress(a,"boom_priority_test_exit"));Marshal.WriteIntPtr(config,40,GetProcAddress(a,"boom_priority_test_exit"));Marshal.WriteIntPtr(config,48,user);
            token=Fn<Start>(m,"boom_threads_start")(r,config);Check(token!=IntPtr.Zero&&WaitForSingleObject(entered,10000)==0,"Owned worker failed");
            Console.WriteLine("priority: owned worker entered");
            // Record24 is observed only by this kernel test, while the worker is gated.
            IntPtr handle=Marshal.ReadIntPtr(token,24);Check(handle!=IntPtr.Zero,"Owned worker handle missing");
            for(int repeat=0;repeat<100;repeat++)for(int p=1;p<=10;p++)Check(priority(r,root,p)==0&&GetThreadPriority(handle)==expected[p-1],"Owned OS priority differs: "+p);
            Console.WriteLine("priority: 1000 owned OS queries passed");
            ulong externalId=next(r);var attach=Fn<Attach>(m,"boom_threads_attach");
            external=new Thread(()=>{
                int original=GetThreadPriority(GetCurrentThread());bool attached=false;
                try {
                    Console.WriteLine("priority: external worker attaching");
                    Check(attach(r,other,externalId)!=IntPtr.Zero,"External attach failed");attached=true;externalIdOS=GetCurrentThreadId();
                    Console.WriteLine("priority: external worker attached");
                    for(int p=10;p>=1;p--){Console.WriteLine("priority: self "+p);Check(priority(r,other,p)==0&&GetThreadPriority(GetCurrentThread())==expected[p-1],"External self priority differs");}
                    SetThreadPriority(GetCurrentThread(),original);
                    ready.Set();Check(done.Wait(15000),"External gate timeout");
                } catch(Exception e){failure=e;ready.Set();}
                finally {if(attached&&detach(r)!=0)failure=new Exception("External detach failed");SetThreadPriority(GetCurrentThread(),original);}
            });external.Start();bool readyNow=ready.Wait(30000);Check(readyNow&&failure==null,"External worker setup failed; ready="+readyNow+": "+failure);
            // External records intentionally have no owned OS HANDLE. The core
            // obtains and closes an operation handle while protecting the record.
            query=OpenThread(0x40,false,externalIdOS);Check(query!=IntPtr.Zero,"External query handle failed");
            for(int p=1;p<=10;p++)Check(priority(r,other,p)==0&&GetThreadPriority(query)==expected[p-1],"Remote external OS priority differs");
            CloseHandle(query);query=IntPtr.Zero;
            racers=new Task<bool>[4];using(var raceReady=new CountdownEvent(4)){
                for(int k=0;k<4;k++)racers[k]=Task.Run(()=>{raceReady.Signal();for(int i=0;i<1000;i++)if(priority(r,other,1+i%10)!=0)return false;return true;});
                Check(raceReady.Wait(10000),"Priority racers did not start");done.Set();
                Check(external.Join(15000)&&failure==null,"External worker cleanup failed: "+failure);external=null;
                Check(Task.WaitAll(racers,15000),"Priority racers did not finish");foreach(var task in racers)Check(task.Result,"Set priority raced unsafely with detach");
            }
            Check(priority(r,other,10)==0,"Detached source oop accessed a stale OS id");
            SetEvent(gate);Check(join(r,token,15000)==0,"Owned worker join failed");
            Check(Fn<Result>(m,"boom_threads_result")(r,token,output)==0&&Marshal.ReadInt64(output)==0&&
                  Marshal.ReadInt32(output,8)==0&&Marshal.ReadInt32(output,40)==0&&
                  Marshal.ReadInt32(output,44)==0&&Marshal.ReadInt32(output,60)==4,
                  "Owned priority worker callback timed out or failed");
            Check(priority(r,root,10)==0,"Finished source priority failed");
            Check(release(r,token)==0,"Owned release failed");token=IntPtr.Zero;Check(priority(r,root,10)==0,"Released source priority failed");
            Check(end(r)==0,"Registry cleanup failed");r=IntPtr.Zero;Check(Fn<HeapDestroy>(m,"boom_heap_destroy")(heap)==1,"Heap cleanup failed");heap=IntPtr.Zero;
        } finally {
            done.Set();SetEvent(gate);if(external!=null)Check(external.Join(25000),"External test still running");
            if(racers!=null)Check(Task.WaitAll(racers,25000),"Priority racers still running");if(query!=IntPtr.Zero)CloseHandle(query);
            if(token!=IntPtr.Zero){Check(join(r,token,25000)==0,"Owned test still running");Check(release(r,token)==0,"Owned teardown release failed");}
            if(r!=IntPtr.Zero)Check(end(r)==0,"Teardown registry failed");if(heap!=IntPtr.Zero)Check(Fn<HeapDestroy>(m,"boom_heap_destroy")(heap)==1,"Teardown heap failed");
            done.Dispose();ready.Dispose();CloseHandle(entered);CloseHandle(gate);Marshal.FreeHGlobal(config);Marshal.FreeHGlobal(user);Marshal.FreeHGlobal(output);FreeLibrary(a);FreeLibrary(m);
        }
    }
}
