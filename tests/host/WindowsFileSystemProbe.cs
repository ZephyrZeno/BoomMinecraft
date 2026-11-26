// VM metadata fixture only. Original Java File/WinNT initializers are not run.
// Field-cache validation and Windows symbol discovery execute the ASM runtime.
using System;
using System.Runtime.InteropServices;
public static class BoomWindowsFileSystemProbe{
    [StructLayout(LayoutKind.Sequential)]struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr GetModuleHandleW(string n);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool GetModuleHandleExW(uint flags,IntPtr address,out IntPtr module);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate void Init(ref Context c,IntPtr p);
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static IntPtr Block(int size){IntPtr p=Marshal.AllocHGlobal(size);Marshal.Copy(new byte[size],0,p,size);return p;}
    static IntPtr Pool(IntPtr layout,uint offset){IntPtr p=Block(48);Marshal.WriteInt32(p,0,0x49534657);Marshal.WriteInt32(p,4,1);Marshal.WriteIntPtr(p,8,layout);Marshal.WriteInt64(p,16,offset);return p;}
    public static void Run(string dll,ulong payload,uint refs,uint fields,uint offset){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),layout=IntPtr.Zero,pool=IntPtr.Zero,bad=IntPtr.Zero;
        Check(m!=IntPtr.Zero,"Windows file system runtime load failed");
        try{
            IntPtr fn=GetProcAddress(m,"boom_winfs_init");Check(fn!=IntPtr.Zero,"Missing native field-cache initializer");var init=Marshal.GetDelegateForFunctionPointer<Init>(fn);
            layout=Block(24);Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,2);Marshal.WriteInt64(layout,8,unchecked((long)payload));Marshal.WriteInt32(layout,16,unchecked((int)refs));Marshal.WriteInt32(layout,20,unchecked((int)fields));pool=Pool(layout,offset);
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};init(ref pending,pool);Check(pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678&&Marshal.ReadInt32(pool,40)==0,"Pending field-cache initialization changed context/state");
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int i=0;i<512;i++){var c=new Context();init(ref c,pool);Check(c.Kind==0&&Marshal.ReadInt32(pool,40)==2,"Concurrent native field-cache initialization failed");}});
            IntPtr create=GetProcAddress(GetModuleHandleW("kernel32.dll"),"CreateFileW"),expectedModule=IntPtr.Zero;Check(create!=IntPtr.Zero&&GetModuleHandleExW(6,create,out expectedModule),"Windows CreateFileW module discovery failed");IntPtr expected=GetProcAddress(expectedModule,"GetFinalPathNameByHandleW");Check(expected!=IntPtr.Zero,"Expected Windows final-path API is absent on test host");
            Check(Marshal.ReadIntPtr(pool,24)==expected&&Marshal.ReadIntPtr(pool,32)==expectedModule,"ASM final-path target/module differs from the OS");
            for(int i=0;i<256;i++){var c=new Context();init(ref c,pool);Check(c.Kind==0&&Marshal.ReadIntPtr(pool,24)==expected,"Idempotent native initialization changed target");}
            bad=Pool(layout,offset);Marshal.WriteInt32(bad,44,1);var reserved=new Context();init(ref reserved,bad);Check(reserved.Kind==7&&Marshal.ReadInt32(bad,40)==0,"Malformed field-cache header accepted");Marshal.WriteInt32(bad,44,0);Marshal.WriteInt64(bad,16,1);var alignment=new Context();init(ref alignment,bad);Check(alignment.Kind==7,"Unaligned File.path accepted");Marshal.WriteInt64(bad,16,checked((long)refs*8));var outside=new Context();init(ref outside,bad);Check(outside.Kind==7,"Scalar/non-reference File.path accepted");
        }finally{if(bad!=IntPtr.Zero)Marshal.FreeHGlobal(bad);if(pool!=IntPtr.Zero)Marshal.FreeHGlobal(pool);if(layout!=IntPtr.Zero)Marshal.FreeHGlobal(layout);if(m!=IntPtr.Zero)FreeLibrary(m);}
    }
}
