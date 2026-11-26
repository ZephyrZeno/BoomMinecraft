// Development FFI only. All conversions execute the assembly provider helper.
using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomConstructorWideningProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Widen(IntPtr ctx,uint from,uint to,ulong bits);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint GetCsr();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void SetCsr(uint bits);
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string image,string oracle) {
        var rows=File.ReadAllLines(oracle).Select(line=>line.Split('\t').Select(ulong.Parse).ToArray()).ToArray();
        Need(rows.Length==456,"Constructor widening oracle coverage changed");
        IntPtr dll=NativeLibrary.Load(image),ctx=Marshal.AllocHGlobal(32);
        var widen=Fn<Widen>(dll,"boom_constructor_widen");var get=Fn<GetCsr>(dll,"boom_widen_probe_get_mxcsr");var set=Fn<SetCsr>(dll,"boom_widen_probe_set_mxcsr");uint original=get();
        int accepted=0,rejected=0,errors=0;long checks=0;
        try {
            foreach(uint csr in new uint[]{0x1f80,0x3f80,0x5f80,0x7f80,0xffc0}) {
                foreach(var row in rows) {
                    Reset(ctx);set(csr);ulong actual=widen(ctx,(uint)row[0],(uint)row[1],row[2]);uint after=get();
                    Need(after==csr,"Widening changed caller MXCSR");
                    Need(actual==row[4]&&Marshal.ReadInt32(ctx)==(int)row[3],"JVM reflection widening differs: from="+row[0]+" to="+row[1]+" bits="+row[2]+" actual="+actual+" expected="+row[4]);
                    checks++;if(csr==0x1f80){if(row[3]==0)accepted++;else rejected++;}
                }
            }
            set(original);Reset(ctx);
            Need(widen(IntPtr.Zero,0,0,1)==0,"Null conversion context accepted");errors++;
            foreach(var pair in new[]{(8U,0U),(0U,8U),(uint.MaxValue,0U)}){Need(widen(ctx,pair.Item1,pair.Item2,1)==0&&Marshal.ReadInt32(ctx)==7,"Invalid conversion kind accepted");errors++;Reset(ctx);}
            Marshal.WriteInt32(ctx,66);Need(widen(ctx,8,8,0)==0&&Marshal.ReadInt32(ctx)==66,"Conversion overwrote pending error");errors++;Reset(ctx);
            const int workers=8,iterations=4096;
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);uint before=get();try{set(0xffc0);for(int i=0;i<iterations;i++){Reset(c);var r=rows[(w+i)%rows.Length];Need(widen(c,(uint)r[0],(uint)r[1],r[2])==r[4]&&Marshal.ReadInt32(c)==(int)r[3]&&get()==0xffc0,"Concurrent constructor widening differs");}}finally{set(before);Marshal.FreeHGlobal(c);}});
            return new long[]{rows.Length,accepted,rejected,checks,errors,workers,workers*iterations};
        } finally {set(original);Marshal.FreeHGlobal(ctx);NativeLibrary.Free(dll);}
    }
}
