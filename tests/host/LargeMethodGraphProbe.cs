// Development-only host for a graph exceeding the original 1024-method cap.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomLargeMethodGraphProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    public static void Run(string dll,int count) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100);if(m==IntPtr.Zero)throw new Exception("Large graph image load");
        try {
            IntPtr p=GetProcAddress(m,"boom_entry");if(p==IntPtr.Zero)throw new Exception("Large graph entry missing");
            var entry=Marshal.GetDelegateForFunctionPointer<Entry>(p);
            int[] seeds={int.MinValue,-1,0,1,7,1024,int.MaxValue,123456789};
            Parallel.For(0,8,worker=>{for(int index=-1;index<=count;index++){
                int seed=seeds[worker],expected=index<0||index>=count?~seed:unchecked(seed*31+index);
                var c=new Context();int actual=unchecked((int)entry(ref c,new[]{(ulong)(uint)index,(ulong)(uint)seed}));
                if(c.Kind!=0||c.Depth!=0||actual!=expected)throw new Exception("Large graph mismatch at "+index+" kind "+c.Kind);
            }});
        }finally{FreeLibrary(m);}
    }
}
