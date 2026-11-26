using System;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

public static class BoomFloatingRemainderProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate ulong Kernel(ulong x,ulong y);
    private static ulong Canonical(ulong bits,bool single) {
        if(single){uint b=(uint)bits;return (b&0x7fffffffU)>0x7f800000U?0x7fc00000UL:b;}
        return (bits&0x7fffffffffffffffUL)>0x7ff0000000000000UL?0x7ff8000000000000UL:bits;
    }
    public static long[] Run(string library,string oracle) {
        IntPtr module=NativeLibrary.Load(library);
        try {
            Kernel single=Marshal.GetDelegateForFunctionPointer<Kernel>(NativeLibrary.GetExport(module,"boom_frem32"));
            Kernel wide=Marshal.GetDelegateForFunctionPointer<Kernel>(NativeLibrary.GetExport(module,"boom_frem64"));
            string[] rows=File.ReadAllLines(oracle);long singles=0,doubles=0;
            ulong[] x=new ulong[rows.Length],y=new ulong[rows.Length],expected=new ulong[rows.Length];bool[] f=new bool[rows.Length];
            for(int i=0;i<rows.Length;i++){
                string[] p=rows[i].Split('\t');f[i]=p[0]=="F";if(f[i])singles++;else doubles++;
                x[i]=ulong.Parse(p[1],NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                y[i]=ulong.Parse(p[2],NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                expected[i]=ulong.Parse(p[3],NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                ulong actual=Canonical((f[i]?single:wide)(x[i],y[i]),f[i]);
                if(actual!=expected[i])throw new Exception("Remainder mismatch row "+i+": "+rows[i]+" native="+actual.ToString("x"));
            }
            Parallel.For(0,8,worker=>{
                for(int i=worker;i<rows.Length;i+=8){
                    ulong actual=Canonical((f[i]?single:wide)(x[i],y[i]),f[i]);
                    if(actual!=expected[i])throw new Exception("Parallel remainder mismatch row "+i);
                }
            });
            return new long[]{singles,doubles,rows.Length,rows.Length*2};
        } finally {NativeLibrary.Free(module);}
    }
}
