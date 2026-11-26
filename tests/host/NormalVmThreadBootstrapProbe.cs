// Test configuration and assertions only. All VM allocation/attachment,
// construction, field publication and failure unwinding execute assembly.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;

public static class BoomNormalVmThreadBootstrapProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Boot(IntPtr ctx,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Current(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Next(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr module,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static void Need(bool v,string text){if(!v)throw new Exception(text);}
    static void Zero(IntPtr p,int bytes){for(int i=0;i<bytes;i+=8)Marshal.WriteInt64(p,i,0);}
    static int Offset(JsonElement s,string owner,string name){
        foreach(var f in s.GetProperty("layouts").GetProperty(owner).GetProperty("fields").EnumerateArray())
            if(f.GetProperty("member").GetProperty("name").GetString()==name)return f.GetProperty("offset").GetInt32();
        throw new Exception("Source field missing: "+owner+"."+name);
    }
    static IntPtr Get(IntPtr o,JsonElement s,string owner,string name){return Marshal.ReadIntPtr(o,Offset(s,owner,name));}
    static string Text(IntPtr str,JsonElement s){
        // String has one reference field at offset zero in the locked normal ABI.
        var bytes=Marshal.ReadIntPtr(str);int size=checked((int)Marshal.ReadInt64(bytes,-16));
        // coder is obtained from the actual String layout by the test config.
        byte coder=Marshal.ReadByte(str,s.GetProperty("string_coder_offset").GetInt32());
        var data=new byte[size];Marshal.Copy(bytes,data,0,size);
        return coder==0?System.Text.Encoding.Latin1.GetString(data):System.Text.Encoding.Unicode.GetString(data);
    }
    public static long[] Run(string configuration){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        var runtime=NativeLibrary.Load(s.GetProperty("runtime").GetString());var image=NativeLibrary.Load(s.GetProperty("image").GetString());
        IntPtr heap=IntPtr.Zero,ctx=Marshal.AllocHGlobal(32),pool=Marshal.AllocHGlobal(192),roots=Marshal.AllocHGlobal(40);
        bool clean=false;var result=new long[19];
        try{
            Zero(ctx,32);Zero(pool,192);Zero(roots,40);
            heap=Fn<Create>(runtime,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<One>(image,"boom_java_string_literals_bind_heap")(heap)==1,"VM thread source heap bind failed");
            var ensure=Fn<Ensure>(runtime,"boom_class_ensure32");
            foreach(var c in s.GetProperty("prerequisite_classes").EnumerateArray()){
                if(ensure(NativeLibrary.GetExport(image,"boom_class"+c.GetInt32()),ctx)!=0||Marshal.ReadInt32(ctx)!=0)break;
                result[9]++;
            }
            var nativePool=NativeLibrary.GetExport(image,"boom_provider_thread_pool");
            Marshal.WriteInt32(pool,0,unchecked((int)0x56544250));Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,12,64);
            Marshal.WriteIntPtr(pool,16,Marshal.ReadIntPtr(nativePool,64));
            Marshal.WriteIntPtr(pool,24,NativeLibrary.GetExport(image,"boom_provider_thread_registry"));
            Marshal.WriteIntPtr(pool,32,roots);Marshal.WriteIntPtr(pool,40,nativePool);
            string[] owners={"java/lang/Thread","java/lang/ThreadGroup","java/security/AccessControlContext"};
            for(int i=0;i<3;i++){
                int id=s.GetProperty("classes").GetProperty(owners[i]).GetInt32();
                Marshal.WriteIntPtr(pool,48+i*8,NativeLibrary.GetExport(image,"boom_layout"+id));
                Marshal.WriteIntPtr(pool,72+i*8,NativeLibrary.GetExport(image,"boom_class"+id));
            }
            int vm=s.GetProperty("classes").GetProperty("jdk/internal/misc/VM").GetInt32();
            Marshal.WriteIntPtr(pool,96,NativeLibrary.GetExport(image,"boom_class"+vm));
            Marshal.WriteIntPtr(pool,104,NativeLibrary.GetExport(image,s.GetProperty("vm_level_symbol").GetString()));
            Marshal.WriteIntPtr(pool,112,NativeLibrary.GetExport(image,"boom_java_string_literal"));
            Marshal.WriteIntPtr(pool,120,NativeLibrary.GetExport(image,"boom_java_string_literal_pool"));
            Marshal.WriteInt32(pool,128,s.GetProperty("main_literal_id").GetInt32());
            Marshal.WriteInt32(pool,132,Offset(s,owners[0],"eetop"));Marshal.WriteInt32(pool,136,Offset(s,owners[0],"holder"));
            Marshal.WriteInt32(pool,140,Offset(s,"java/lang/Thread$FieldHolder","threadStatus"));
            int at=144;foreach(var c in s.GetProperty("constructors").EnumerateArray()){Marshal.WriteIntPtr(pool,at,NativeLibrary.GetExport(image,c.GetProperty("symbol").GetString()));at+=8;}
            Marshal.WriteInt32(pool,176,Offset(s,owners[0],"tid"));
            var main=Marshal.ReadInt32(ctx)==0?Fn<Boot>(runtime,"boom_vm_thread_bootstrap")(ctx,pool):IntPtr.Zero;
            result[10]=Marshal.ReadInt32(pool,8);
            if(Marshal.ReadInt32(ctx)==0){
                Need(main!=IntPtr.Zero&&main==Marshal.ReadIntPtr(roots)&&result[10]==2,"Normal primordial bootstrap did not publish");
                var registry=Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,24));
                Need(registry!=IntPtr.Zero&&Fn<Current>(runtime,"boom_threads_current")(registry)==main,"Original main/current identity differs");
                // Observe the live counter without reserving a child ID before System.
                Need(Marshal.ReadInt64(registry,32)==2,"Original primordial constructor consumed a child ID");
                Need(Marshal.ReadInt64(main,Offset(s,owners[0],"tid"))==1&&Text(Get(main,s,owners[0],"name"),s)=="main","Original main Thread ID/name differs");
                var holder=Get(main,s,owners[0],"holder");var group=Marshal.ReadIntPtr(roots,16);var system=Marshal.ReadIntPtr(roots,8);var acc=Marshal.ReadIntPtr(roots,24);
                Need(holder!=IntPtr.Zero&&Get(holder,s,"java/lang/Thread$FieldHolder","group")==group,"Original FieldHolder group differs");
                Need(Marshal.ReadInt32(holder,Offset(s,"java/lang/Thread$FieldHolder","threadStatus"))==4&&Marshal.ReadInt32(holder,Offset(s,"java/lang/Thread$FieldHolder","priority"))==5,"Original holder or VM RUNNABLE publication differs");
                Need(Get(group,s,owners[1],"parent")==system&&Get(system,s,owners[1],"parent")==IntPtr.Zero&&Text(Get(group,s,owners[1],"name"),s)=="main"&&Text(Get(system,s,owners[1],"name"),s)=="system","Original ThreadGroup hierarchy differs");
                Need(Get(main,s,owners[0],"inheritedAccessControlContext")==acc&&Get(acc,s,owners[2],"context")==IntPtr.Zero&&Marshal.ReadByte(acc,Offset(s,owners[2],"isPrivileged"))==1&&Marshal.ReadByte(acc,Offset(s,owners[2],"isAuthorized"))==1,"Original authorized bootstrap ACC differs");
                Need(Get(main,s,owners[0],"interruptLock")!=IntPtr.Zero&&Get(main,s,owners[0],"scopedValueBindings")!=IntPtr.Zero,"Original main constructor fields missing");
                result[11]=1;
                if(s.GetProperty("continue_System_phase1").GetBoolean()){
                    result[17]=1;
                    Fn<Entry>(image,s.GetProperty("system_entry_symbol").GetString())(ctx,IntPtr.Zero);
                    result[18]=Marshal.ReadInt32(ctx)==0?1:0;
                }
            }
            var diagnostic=NativeLibrary.GetExport(image,"boom_diagnostic_pool");
            for(int i=0;i<4;i++)result[i]=Marshal.ReadInt32(ctx,i*4);
            result[4]=Marshal.ReadInt32(diagnostic,8);result[5]=Marshal.ReadInt32(diagnostic,32);
            result[6]=Marshal.ReadInt32(diagnostic,44);result[7]=Marshal.ReadInt32(diagnostic,48);result[8]=Marshal.ReadInt32(diagnostic,52);
            result[12]=Marshal.ReadInt64(heap,56);result[14]=Marshal.ReadInt64(heap,112);result[15]=Marshal.ReadInt32(heap,104);
            // Test-process cleanup, not a Java Thread.exit replacement.
            var reg=Marshal.ReadIntPtr(NativeLibrary.GetExport(image,"boom_provider_thread_registry"));
            if(reg!=IntPtr.Zero){
                Need(Fn<One>(runtime,"boom_threads_detach")(reg)==0,"VM bootstrap test detach failed");
                Need(Fn<One>(image,"boom_provider_thread_bind")(IntPtr.Zero)==0,"VM bootstrap test unbind failed");
                Need(Fn<One>(runtime,"boom_threads_destroy")(reg)==0,"VM bootstrap test registry destroy failed");
            }
            result[16]=Marshal.ReadIntPtr(NativeLibrary.GetExport(image,"boom_provider_thread_registry"))==IntPtr.Zero?1:0;
            Need(Fn<Release>(image,"boom_release_trace_pool")()==0,"VM bootstrap retained Java frames");
            int freed=Fn<One>(runtime,"boom_heap_destroy")(heap);result[13]=freed==1?1:0;
            if(freed!=1)Need(result[0]==0xB001&&result[4]==2&&result[14]>0&&result[15]==0,"VM bootstrap cleanup failed without a recorded monitor-owning source stop");
            clean=freed==1;heap=IntPtr.Zero;return result;
        }finally{
            if(heap!=IntPtr.Zero)Fn<One>(runtime,"boom_heap_destroy")(heap);
            Marshal.FreeHGlobal(ctx);Marshal.FreeHGlobal(pool);Marshal.FreeHGlobal(roots);
            if(clean){NativeLibrary.Free(image);NativeLibrary.Free(runtime);}
        }
    }
}
