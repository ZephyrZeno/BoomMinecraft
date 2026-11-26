// VM bootstrap controller. Thread/FieldHolder/ThreadGroup/ACC constructors run ASM.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
public static class BoomPrimordialThreadProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RegCreate(IntPtr h,uint max);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Next(IntPtr r);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Current(IntPtr r);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint c,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string name){IntPtr p=GetProcAddress(m,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static string Text(IntPtr value){IntPtr chars=Marshal.ReadIntPtr(value);return Marshal.PtrToStringUni(chars,checked((int)Marshal.ReadInt64(chars,-16)/2));}
    // Thread offsets: holder,tid,name,interruptLock,inheritedACC,scopedBindings.
    // Holder: group,task,stackSize,priority,daemon,status; ACC: context,privileged,authorized.
    public static void Run(string image,uint threadClass,uint markerField,int[] t,int[] h,int[] a,uint vmClass,uint levelField,bool rejectBooted=false){
        if(rejectBooted){string copy=Path.Combine(Path.GetDirectoryName(image),"wrong-phase.dll");File.Copy(image,copy,true);image=copy;}
        IntPtr m=LoadLibraryExW(image,IntPtr.Zero,0x1100),heap=IntPtr.Zero,reg=IntPtr.Zero;bool attached=false;
        Check(m!=IntPtr.Zero,"Primordial image load failed");
        try{
            heap=Fn<Create>(m,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Primordial heap bind failed");
            reg=Fn<RegCreate>(m,"boom_threads_create")(heap,32);Check(reg!=IntPtr.Zero&&Fn<One>(m,"boom_bind_thread_registry")(reg)==0,"Primordial registry bind failed");
            if(rejectBooted)Marshal.WriteInt64(Fn<Field>(m,"boom_get_static_field")(vmClass,levelField),1);
            var entry=Fn<Entry>(m,GetProcAddress(m,"boom_entry32")!=IntPtr.Zero?"boom_entry32":"boom_entry");var c=new Context();ulong result=entry(ref c,Array.Empty<ulong>());IntPtr obj=new IntPtr(unchecked((long)result));
            if(rejectBooted){Check(result==0&&c.Kind!=0&&Fn<Current>(m,"boom_threads_current")(reg)==IntPtr.Zero,"Primordial phase guard failed to reject/roll back attachment");return;}
            Check(result!=0&&c.Kind==0&&c.Depth==0,"Primordial constructor failed: kind="+c.Kind+" method="+c.Method+" pc="+c.PC);attached=true;
            Check(Fn<Current>(m,"boom_threads_current")(reg)==obj,"Primordial current identity differs");
            Check(Marshal.ReadIntPtr(obj,-8)==Fn<Layout>(m,"boom_get_object_layout")(threadClass),"Primordial Thread type differs");
            IntPtr holder=Marshal.ReadIntPtr(obj,t[0]);Check(holder!=IntPtr.Zero,"Original Thread did not construct FieldHolder");
            Check(Marshal.ReadInt64(obj,t[1])==1&&Text(Marshal.ReadIntPtr(obj,t[2]))=="main","Original Thread ID/name differ");
            Check(Marshal.ReadIntPtr(obj,t[3])!=IntPtr.Zero,"Original interrupt lock missing");
            Check(Marshal.ReadIntPtr(holder,h[0])!=IntPtr.Zero&&Marshal.ReadIntPtr(holder,h[1])==IntPtr.Zero&&Marshal.ReadInt64(holder,h[2])==0&&Marshal.ReadInt32(holder,h[3])==5&&Marshal.ReadByte(holder,h[4])==0&&Marshal.ReadInt32(holder,h[5])==5,"Original holder fields/VM alive publication differ");
            IntPtr acc=Marshal.ReadIntPtr(obj,t[4]);Check(acc!=IntPtr.Zero&&Marshal.ReadIntPtr(acc,a[0])==IntPtr.Zero&&Marshal.ReadByte(acc,a[1])==1&&Marshal.ReadByte(acc,a[2])==1,"Explicit original bootstrap access context differs");
            Check(Marshal.ReadIntPtr(obj,t[5])==Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(threadClass,markerField)),"Original scoped binding marker differs");
            Check(Fn<Next>(m,"boom_threads_next_id")(reg)==2,"Primordial constructor consumed a normal Thread ID");
            var second=new Context();Check(entry(ref second,Array.Empty<ulong>())==0&&second.Kind!=0&&Fn<Current>(m,"boom_threads_current")(reg)==obj,"Primordial entry replaced an attached thread");
            Check(Fn<One>(m,"boom_threads_detach")(reg)==0,"Primordial detach failed");attached=false;
            IntPtr statics=Fn<Roots>(m,"boom_get_static_roots")(out uint n);var all=new List<IntPtr>{obj};for(int i=0;i<n;i++)all.Add(Marshal.ReadIntPtr(statics,i*8));var todo=new Stack<IntPtr>(all);var seen=new HashSet<IntPtr>();while(todo.Count>0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint refs=unchecked((uint)Marshal.ReadInt32(p,-20));for(uint i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,checked((int)i*8)));}
            IntPtr roots=Marshal.AllocHGlobal(all.Count*8);try{for(int i=0;i<all.Count;i++)Marshal.WriteIntPtr(roots,i*8,all[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,(uint)all.Count)!=ulong.MaxValue&&(ulong)Marshal.ReadInt64(heap,56)==(ulong)seen.Count,"Primordial independent root graph differs");}finally{Marshal.FreeHGlobal(roots);}
            Check(Text(Marshal.ReadIntPtr(obj,t[2]))=="main"&&Marshal.ReadInt64(obj,t[1])==1,"Primordial fields lost after GC");
            Check(Fn<One>(m,"boom_bind_thread_registry")(IntPtr.Zero)==0&&Fn<One>(m,"boom_threads_destroy")(reg)==0,"Primordial registry shutdown failed");reg=IntPtr.Zero;
        }finally{if(attached)Fn<One>(m,"boom_threads_detach")(reg);if(reg!=IntPtr.Zero){Fn<One>(m,"boom_bind_thread_registry")(IntPtr.Zero);Fn<One>(m,"boom_threads_destroy")(reg);}IntPtr release=GetProcAddress(m,"boom_release_trace_pool");if(release!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<Release>(release)()==0,"Primordial frames remain active");if(heap!=IntPtr.Zero)Check(Fn<One>(m,"boom_heap_destroy")(heap)!=0,"Primordial heap shutdown failed");FreeLibrary(m);}
    }
}
