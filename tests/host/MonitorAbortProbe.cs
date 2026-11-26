// Isolated native teardown kernel test; no original Java method is substituted.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;

public static class BoomMonitorAbortProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Allocate(IntPtr h,ulong bytes,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr h,uint n,uint kind,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Monitor(IntPtr h,IntPtr o,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Abort(IntPtr h,IntPtr ctx,IntPtr released,uint auth);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Contains(IntPtr h,IntPtr o);
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Clear(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);}
    static IntPtr Node(IntPtr heap,IntPtr obj){var n=Marshal.ReadIntPtr(heap,96);for(int i=0;n!=IntPtr.Zero&&i<1024;i++,n=Marshal.ReadIntPtr(n,8))if(Marshal.ReadIntPtr(n)==obj)return n;throw new Exception("Monitor node missing");}
    public static void Run(string runtime,string kernel){
        var r=NativeLibrary.Load(runtime);var k=NativeLibrary.Load(kernel);IntPtr heap=IntPtr.Zero;
        var ctx=Marshal.AllocHGlobal(32);var control=Marshal.AllocHGlobal(32);var released=Marshal.AllocHGlobal(8);var roots=Marshal.AllocHGlobal(24);
        var enter=Fn<Monitor>(r,"boom_monitor_enter");var exit=Fn<Monitor>(r,"boom_monitor_exit");var notify=Fn<Monitor>(r,"boom_monitor_notify_all");var abort=Fn<Abort>(k,"boom_monitor_abort_owned");
        var owned=new Dictionary<IntPtr,int>();Thread worker=null;Exception error=null;var ready=new ManualResetEventSlim(false);var finish=new ManualResetEventSlim(false);
        Action<IntPtr> take=o=>{Clear(ctx);Check(enter(heap,o,ctx)==0,"Monitor enter failed");owned[o]=owned.ContainsKey(o)?owned[o]+1:1;};
        try {
            heap=Fn<HeapCreate>(r,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero,"Heap creation failed");Clear(ctx);
            var a=Fn<Allocate>(r,"boom_heap_alloc")(heap,16,0,265);var b=Fn<ArrayNew>(r,"boom_array_new")(heap,4,10,ctx);var c=Fn<Allocate>(r,"boom_heap_alloc")(heap,16,0,265);
            Check(a!=IntPtr.Zero&&b!=IntPtr.Zero&&c!=IntPtr.Zero,"VM storage allocation failed");
            worker=new Thread(()=>{var wc=Marshal.AllocHGlobal(32);bool held=false;try{Clear(wc);Check(enter(heap,c,wc)==0,"Other owner enter failed");held=true;ready.Set();finish.Wait();}catch(Exception ex){error=ex;ready.Set();}finally{if(held){Clear(wc);if(exit(heap,c,wc)!=0)error=new Exception("Other owner exit failed");}Marshal.FreeHGlobal(wc);}});worker.Start();
            Check(ready.Wait(10000)&&error==null,"Other OS owner was not ready");take(a);take(a);take(b);
            foreach(var mode in new[]{new[]{0,0,0},new[]{16,0,0},new[]{17,0,0},new[]{0xb001,1,0},new[]{0xb002,0,0}}){
                Clear(control);Marshal.WriteInt32(control,mode[0]);Marshal.WriteInt32(control,12,mode[1]);if(mode[0]==16)Marshal.WriteIntPtr(control,16,a);
                Check(abort(heap,control,released,(uint)mode[2])==87&&Marshal.ReadInt64(released)==0&&Marshal.ReadInt64(heap,112)==4,"Ordinary/unwinding/unauthorized context released monitors");
            }
            Clear(control);Marshal.WriteInt32(control,0,0xb001);Marshal.WriteInt32(control,4,37);Marshal.WriteInt32(control,8,73);Marshal.WriteInt64(control,24,0x1122334455667788);
            var node=Node(heap,a);Marshal.WriteInt32(node,28,1);
            try{Check(abort(heap,control,released,0)==50&&Marshal.ReadInt64(heap,112)==4&&Marshal.ReadInt32(node,20)==2,"Unsupported wait metadata caused partial release");}finally{Marshal.WriteInt32(node,28,0);}
            Marshal.WriteInt64(heap,112,2);try{Check(abort(heap,control,released,0)==87&&Marshal.ReadInt32(node,20)==2,"Invalid monitor accounting caused partial release");}finally{Marshal.WriteInt64(heap,112,4);}
            var before=new byte[32];var after=new byte[32];Marshal.Copy(control,before,0,32);
            Check(abort(heap,control,released,0)==0&&Marshal.ReadInt64(released)==3&&Marshal.ReadInt64(heap,112)==1,"Owned recursive acquisitions were not released exactly");owned.Clear();
            Marshal.Copy(control,after,0,32);for(int i=0;i<32;i++)Check(before[i]==after[i],"Abort modified diagnostic Context or VM plan");
            Clear(ctx);Check(notify(heap,c,ctx)==17,"Abort stole another OS thread's monitor");
            finish.Set();Check(worker.Join(10000)&&error==null,"Other owner failed to finish");worker=null;
            take(a);Clear(control);Marshal.WriteInt32(control,0,0xb002);Check(abort(heap,control,released,1)==0&&Marshal.ReadInt64(released)==1,"Authorized stop cleanup failed");owned.Clear();

            take(a);take(a);error=null;ready.Reset();
            worker=new Thread(()=>{var wc=Marshal.AllocHGlobal(32);bool held=false;try{Clear(wc);ready.Set();Check(enter(heap,a,wc)==0,"Blocked contender failed to acquire");held=true;Check(notify(heap,a,wc)==0,"Woken contender did not own monitor");}catch(Exception ex){error=ex;}finally{if(held){Clear(wc);if(exit(heap,a,wc)!=0)error=new Exception("Contender exit failed");}Marshal.FreeHGlobal(wc);}});worker.Start();
            Check(ready.Wait(10000)&&SpinWait.SpinUntil(()=>Marshal.ReadInt32(Node(heap,a),24)>0,10000),"Contender did not register native wait");
            Clear(control);Marshal.WriteInt32(control,0,0xb001);Check(abort(heap,control,released,0)==0&&Marshal.ReadInt64(released)==2,"Contended monitor abort failed");owned.Clear();
            Check(worker.Join(10000)&&error==null,"Controlled abort did not wake monitor contender");worker=null;
            Check(Marshal.ReadInt64(heap,112)==0&&Marshal.ReadIntPtr(heap,96)==IntPtr.Zero&&Marshal.ReadInt32(heap,104)==0,"Active monitor list or count leaked");
            Marshal.WriteIntPtr(roots,0,a);Marshal.WriteIntPtr(roots,8,b);Marshal.WriteIntPtr(roots,16,c);
            Check(Fn<Collect>(r,"boom_heap_collect")(heap,roots,3)>0,"Idle monitor nodes were not reclaimable");
            var contains=Fn<Contains>(r,"boom_heap_contains");Check(contains(heap,a)==1&&contains(heap,b)==1&&contains(heap,c)==1,"Monitor cleanup damaged live receivers");
            Check(Fn<HeapDestroy>(r,"boom_heap_destroy")(heap)==1,"Heap cleanup failed");heap=IntPtr.Zero;
        }finally{
            finish.Set();foreach(var pair in owned)for(int i=0;i<pair.Value;i++){Clear(ctx);Check(exit(heap,pair.Key,ctx)==0,"Main monitor teardown failed");}
            if(worker!=null)Check(worker.Join(15000),"Native monitor worker still active");
            if(heap!=IntPtr.Zero)Check(Fn<HeapDestroy>(r,"boom_heap_destroy")(heap)==1,"Heap teardown failed");
            ready.Dispose();finish.Dispose();Marshal.FreeHGlobal(roots);Marshal.FreeHGlobal(released);Marshal.FreeHGlobal(control);Marshal.FreeHGlobal(ctx);NativeLibrary.Free(k);NativeLibrary.Free(r);
        }
    }
}
