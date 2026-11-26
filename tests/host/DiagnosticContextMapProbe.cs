// Isolated development ABI test, not original Java/game execution evidence.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

public static class BoomDiagnosticContextMapProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Record(IntPtr c,uint row,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Row(IntPtr c,IntPtr pool);
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static void Zero(IntPtr p,int n){for(int i=0;i<n;i+=8)Marshal.WriteInt64(p,i,0);}
    public static void Run(string path){
        var lib=NativeLibrary.Load(path);var record=Marshal.GetDelegateForFunctionPointer<Record>(NativeLibrary.GetExport(lib,"boom_diagnostic_context_map_record"));
        var row=Marshal.GetDelegateForFunctionPointer<Row>(NativeLibrary.GetExport(lib,"boom_diagnostic_context_map_row"));
        var pool=Marshal.AllocHGlobal(64);var slots=Marshal.AllocHGlobal(64*16);var context=Marshal.AllocHGlobal(32);
        IntPtr[] contexts=new IntPtr[8];
        Action reset=()=>{Zero(pool,64);Zero(slots,64*16);Marshal.WriteInt32(pool,0,0x504d4344);Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,8,64);Marshal.WriteInt32(pool,12,64);Marshal.WriteIntPtr(pool,16,slots);};
        try{
            reset();Zero(context,32);Marshal.WriteInt32(context,0,0xb001);Marshal.WriteInt32(context,4,37);Marshal.WriteInt32(context,8,73);Marshal.WriteInt64(context,24,0x1122334455667788);
            var before=new byte[32];var after=new byte[32];Marshal.Copy(context,before,0,32);
            Check(record(context,1,pool)==1&&row(context,pool)==1,"Context row not recorded");
            Check(record(context,2,pool)==1&&row(context,pool)==2&&Marshal.ReadInt32(pool,24)==1,"Context update created a duplicate key");
            Marshal.Copy(context,after,0,32);for(int i=0;i<32;i++)Check(before[i]==after[i],"Context32 or VM exception-plan pointer changed");
            Check(record(IntPtr.Zero,3,pool)==0&&record(context,0,pool)==0&&record(context,3,IntPtr.Zero)==0,"Invalid row arguments accepted");
            Check(row(IntPtr.Zero,pool)==0&&row(new IntPtr(0x12340),pool)==0,"Unknown key returned a row");
            foreach(var change in new[]{new[]{0,0},new[]{4,2},new[]{8,0},new[]{8,3},new[]{8,131072},new[]{12,0},new[]{12,65},new[]{32,1}}){
                reset();Marshal.WriteInt32(pool,change[0],change[1]);Check(record(context,4,pool)==0&&row(context,pool)==0,"Invalid sidecar metadata accepted");
            }
            reset();Marshal.WriteIntPtr(pool,16,IntPtr.Add(slots,1));Check(record(context,4,pool)==0,"Unaligned slot table accepted");
            reset();
            for(int i=0;i<64;i++)Check(record(new IntPtr(0x1000L*(i+1)),(uint)(i+1),pool)==1,"Linear-probe collision lost a row");
            for(int i=0;i<64;i++)Check(row(new IntPtr(0x1000L*(i+1)),pool)==i+1,"Collision lookup differs");
            Check(record(new IntPtr(0x1000L*65),65,pool)==0&&Marshal.ReadInt32(pool,24)==64&&Marshal.ReadInt32(pool,28)==1,"Full map overflow was silent or unbounded");
            Check(row(new IntPtr(0x1000L*65),pool)==0,"Missing lookup failed to terminate in a full table");
            reset();Marshal.WriteInt32(pool,12,4);for(int i=0;i<4;i++)Check(record(new IntPtr(0x1000L*(i+1)),(uint)(i+1),pool)==1,"Probe limit rejected an available slot");
            Check(record(new IntPtr(0x5000),5,pool)==0&&Marshal.ReadInt32(pool,28)==1,"Probe budget exceeded");
            reset();for(int i=0;i<8;i++){contexts[i]=Marshal.AllocHGlobal(32);Zero(contexts[i],32);Marshal.WriteInt64(contexts[i],24,0x1122334455667788);}
            Parallel.For(0,8,w=>{for(int i=0;i<1024;i++){uint id=(uint)(w*10000+i+1);Check(record(contexts[w],id,pool)==1&&row(contexts[w],pool)==id,"Parallel context rows interfered");}});
            Check(Marshal.ReadInt32(pool,24)==8&&Marshal.ReadInt32(pool,28)==0,"Parallel row accounting differs");
            for(int i=0;i<8;i++)Check(Marshal.ReadInt64(contexts[i],24)==0x1122334455667788,"Parallel row record modified VM configuration");
            reset();Parallel.For(0,8,w=>{for(int i=0;i<1024;i++)Check(record(context,(uint)(w+1),pool)==1,"Contended publication failed");});
            Check(Marshal.ReadInt32(pool,24)==1&&row(context,pool)>=1&&row(context,pool)<=8&&Marshal.ReadInt32(pool,28)==0,"Same-key CAS publication duplicated entries");
        }finally{foreach(var p in contexts)if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);Marshal.FreeHGlobal(context);Marshal.FreeHGlobal(slots);Marshal.FreeHGlobal(pool);NativeLibrary.Free(lib);}
    }
}
