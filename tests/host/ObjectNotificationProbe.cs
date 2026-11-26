// Kernel adapter test only. The fixture's unused class descriptor is never run.
using System;
using System.Runtime.InteropServices;
using System.Threading;

public static class BoomObjectNotificationProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Allocate(IntPtr heap,ulong bytes,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr heap,uint length,uint kind,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Monitor(IntPtr heap,IntPtr obj,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Service(IntPtr ctx,IntPtr argv,IntPtr pool,uint op);
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Clear(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static void Run(string runtime,string adapter){
        var r=NativeLibrary.Load(runtime);var m=NativeLibrary.Load(adapter);IntPtr heap=IntPtr.Zero;
        var ctx=Marshal.AllocHGlobal(32);var other=Marshal.AllocHGlobal(32);var argv=Marshal.AllocHGlobal(8);
        var enter=Fn<Monitor>(r,"boom_monitor_enter");var exit=Fn<Monitor>(r,"boom_monitor_exit");
        var service=Fn<Service>(m,"boom_provider_object_notification_service");var pool=NativeLibrary.GetExport(m,"boom_provider_object_notification_pool");
        var cell=NativeLibrary.GetExport(m,"boom_heap_ptr");IntPtr active=IntPtr.Zero,node=IntPtr.Zero;int depth=0;
        try {
            Clear(ctx);Clear(other);heap=Fn<HeapCreate>(r,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero,"Heap allocation failed");Marshal.WriteIntPtr(cell,heap);
            var obj=Fn<Allocate>(r,"boom_heap_alloc")(heap,16,0,265);var array=Fn<ArrayNew>(r,"boom_array_new")(heap,4,10,ctx);
            Check(obj!=IntPtr.Zero&&array!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Receiver allocation failed");
            foreach(var receiver in new[]{obj,array}){
                active=receiver;Marshal.WriteIntPtr(argv,receiver);
                for(uint op=0;op<2;op++){Clear(ctx);Check(service(ctx,argv,pool,op)==17&&Marshal.ReadInt32(ctx)==17,"Unowned notify did not report monitor ownership error");}
                Clear(ctx);Check(enter(heap,receiver,ctx)==0,"First recursive enter failed");depth++;
                Check(enter(heap,receiver,ctx)==0,"Second recursive enter failed");depth++;
                for(uint op=0;op<2;op++){Clear(ctx);Check(service(ctx,argv,pool,op)==0&&Marshal.ReadInt32(ctx)==0,"Owned notify failed");}
                uint wrongResult=0;Exception error=null;
                var thread=new Thread(()=>{try{Clear(other);wrongResult=(uint)service(other,argv,pool,1);}catch(Exception ex){error=ex;}});thread.Start();
                Check(thread.Join(10000)&&error==null&&wrongResult==17&&Marshal.ReadInt32(other)==17,"Another OS thread notified an owned monitor");
                node=Marshal.ReadIntPtr(heap,96);while(node!=IntPtr.Zero&&Marshal.ReadIntPtr(node)!=receiver)node=Marshal.ReadIntPtr(node,8);
                Check(node!=IntPtr.Zero,"Active receiver monitor absent");Marshal.WriteInt32(node,28,1);
                for(uint op=0;op<2;op++){Clear(ctx);Check(service(ctx,argv,pool,op)==20&&Marshal.ReadInt32(ctx)==20,"Unsupported wait metadata was silently accepted");}
                Marshal.WriteInt32(node,28,0);node=IntPtr.Zero;
                Clear(ctx);Check(exit(heap,receiver,ctx)==0,"Recursive exit failed");depth--;
                Check(service(ctx,argv,pool,1)==0,"Partial recursive exit lost monitor ownership");
                Check(exit(heap,receiver,ctx)==0,"Final exit failed");depth--;active=IntPtr.Zero;
            }
            Marshal.WriteIntPtr(argv,IntPtr.Zero);Clear(ctx);Check(service(ctx,argv,pool,1)==4&&Marshal.ReadInt32(ctx)==4,"Null receiver error differs from core");
            Marshal.WriteIntPtr(argv,obj);Clear(ctx);Marshal.WriteInt32(ctx,99);Check(service(ctx,argv,pool,0)==0&&Marshal.ReadInt32(ctx)==99,"Pending error was overwritten");
            Clear(ctx);Check(service(ctx,argv,pool,2)==0&&Marshal.ReadInt32(ctx)==7,"Unknown operation accepted");
            Check(Marshal.ReadInt64(heap,112)==0&&Marshal.ReadInt32(heap,104)==0,"Monitor acquisition or registry lock leaked");
            Marshal.WriteIntPtr(cell,IntPtr.Zero);Check(Fn<HeapDestroy>(r,"boom_heap_destroy")(heap)==1,"Heap cleanup failed");heap=IntPtr.Zero;
        }finally{
            if(node!=IntPtr.Zero)Marshal.WriteInt32(node,28,0);
            while(depth>0){Clear(ctx);Check(exit(heap,active,ctx)==0,"Monitor teardown failed");depth--;}
            Marshal.WriteIntPtr(cell,IntPtr.Zero);if(heap!=IntPtr.Zero)Check(Fn<HeapDestroy>(r,"boom_heap_destroy")(heap)==1,"Heap teardown failed");
            Marshal.FreeHGlobal(argv);Marshal.FreeHGlobal(other);Marshal.FreeHGlobal(ctx);NativeLibrary.Free(m);NativeLibrary.Free(r);
        }
    }
}
