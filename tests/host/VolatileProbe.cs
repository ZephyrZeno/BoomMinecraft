// Development orchestration only. Both actor threads and the controller loop
// execute native MASM; no managed transition/fence occurs inside a Java actor.
using System;
using System.Runtime.InteropServices;
public static class BoomVolatileProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Stress(IntPtr entry,uint count,IntPtr output,uint resetMode);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context ctx,[In] ulong[] values);
    static void Check(bool pass,string message){if(!pass)throw new Exception(message);}
    static IntPtr Open(string path){IntPtr value=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(value!=IntPtr.Zero,"Volatile module load failed: "+path);return value;}
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static long Run(string dll,string harness,uint count,uint mode,bool requireOrdering) {
        IntPtr module=Open(dll),probe=IntPtr.Zero,heap=IntPtr.Zero,output=IntPtr.Zero;
        try {
            probe=Open(harness);var stress=Fn<Stress>(probe,"boom_volatile_stress");
            Check(stress(IntPtr.Zero,1,IntPtr.Zero,0)==87,"Invalid harness arguments accepted");
            heap=Fn<Create>(module,"boom_heap_create")(64*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Volatile heap setup failed");
            output=Marshal.AllocHGlobal(checked((int)count*64));IntPtr entry=GetProcAddress(module,"boom_entry");
            int status=stress(entry,count,output,mode);Check(status==0,"Native actor harness failed: "+status+" mode="+mode);
            long forbidden=0;
            for(int i=0;i<count;i++){
                IntPtr a=IntPtr.Add(output,i*64),b=IntPtr.Add(a,32);
                ulong left=unchecked((ulong)Marshal.ReadInt64(a)),right=unchecked((ulong)Marshal.ReadInt64(b));
                for(int n=8;n<32;n+=8)Check(Marshal.ReadInt64(a,n)==0&&Marshal.ReadInt64(b,n)==0,"Actor exception/context/tail changed at "+i);
                if(mode==0||mode==3){
                    Check(left<=1&&right<=1,"Invalid store-buffer outcome");
                    if(left==0&&right==0)forbidden++;
                } else if(mode==6||mode==9)Check(left==0&&right==0x12345678UL,"Published ordinary state was stale: "+left+","+right+" at "+i);
                else if(mode==12||mode==15)Check(left==0&&right==0,"Volatile tearing/neighbor mismatch");
                else throw new Exception("Unknown probe mode");
            }
            if(requireOrdering)Check(forbidden==0,"Forbidden volatile store-buffer outcome occurred "+forbidden+" times");
            if(mode==15){var ctx=new Context();Check(Fn<Entry>(module,"boom_entry")(ref ctx,new ulong[]{18})==32512&&ctx.Kind==0,"Adjacent narrow volatile fields clobbered each other");}
            uint rootCount;IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out rootCount);
            long expected=mode==9?2:1;
            Check(Marshal.ReadInt64(heap,56)==(mode==9?count+1:1),"Unexpected volatile allocation count");
            ulong freed=Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount);
            Check(Marshal.ReadInt64(heap,56)==expected&&freed==(mode==9?count-1U:0U),"Volatile-published graph was not preserved/reclaimed correctly");
            if(mode==9){var ctx=new Context();Check(Fn<Entry>(module,"boom_entry")(ref ctx,new ulong[]{11})==0x12345678&&ctx.Kind==0,"Published reference changed after GC");}
            return forbidden;
        } finally {if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(probe!=IntPtr.Zero)FreeLibrary(probe);FreeLibrary(module);}
    }
}
