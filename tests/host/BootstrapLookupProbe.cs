// CLI controller only; original ClassLoader wrapper and native lookup run in ASM.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomBootstrapLookupProbe {
    [StructLayout(LayoutKind.Sequential)]struct Context { public uint Kind,PC,Method,Depth;public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Entry(ref Context c,[In]ulong[] argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static IntPtr Text(Alloc alloc,IntPtr heap,IntPtr pool,string text){if(text==null)return IntPtr.Zero;IntPtr data=alloc(heap,(ulong)text.Length*2,0,261),value=alloc(heap,16,1,Bits(Marshal.ReadIntPtr(pool,40)));Check(data!=IntPtr.Zero&&value!=IntPtr.Zero,"Lookup input allocation failed");for(int i=0;i<text.Length;i++)Marshal.WriteInt16(data,i*2,unchecked((short)text[i]));Marshal.WriteIntPtr(value,data);return value;}
    public static string[] Run(string dll,string runtime,string[] names,string unlinked,uint uleClass){
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"Bootstrap lookup images failed to load");
        try {
            heap=Fn<Create>(rt,"boom_heap_create")(33554432);Check(heap!=IntPtr.Zero&&Fn<One>(image,"boom_bind_heap")(heap)==1,"Bootstrap lookup heap bind failed");
            IntPtr lookup=Fn<Pointer>(image,"boom_get_for_name_pool")(),strings=Marshal.ReadIntPtr(lookup,16),mirrors=Marshal.ReadIntPtr(lookup,8);
            var alloc=Fn<Alloc>(rt,"boom_heap_alloc");var entry=Fn<Entry>(image,"boom_entry32");string[] cases={"java.lang.Object","java.lang.String","java.lang.Class","java.lang.Throwable","java.lang.ClassLoader","dev.boom.MissingBootstrap","","[I","[Ljava.lang.String;","java/lang/String","java.sql.Driver","int",null,"java.lang.Str\0ing","java.lang.Ｓtring"};
            IntPtr[] inputs=new IntPtr[cases.Length];for(int i=0;i<cases.Length;i++)inputs[i]=Text(alloc,heap,strings,cases[i]);
            Func<int,string> invoke=i=>{var c=new Context();IntPtr result=entry(ref c,new[]{Bits(inputs[i])});Check(c.Depth==0,"Bootstrap lookup leaked frames");Check(c.Kind==0,"Bootstrap lookup failed case="+i+" kind="+c.Kind+" method="+c.Method+" pc="+c.PC);if(result==IntPtr.Zero)return "null";Check(Marshal.ReadIntPtr(result,-8)==Marshal.ReadIntPtr(mirrors,32),"Bootstrap result is not Class");int id=Marshal.ReadInt32(result);Check(id>=0&&id<names.Length&&Marshal.ReadIntPtr(Marshal.ReadIntPtr(mirrors,16),id*8)==result,"Bootstrap mirror is not canonical");return names[id];};
            string[] results=new string[cases.Length];for(int i=0;i<cases.Length;i++)results[i]=invoke(i);
            IntPtr uleTag=Fn<Indexed>(image,"boom_get_object_layout")(uleClass);Check(uleTag!=IntPtr.Zero,"Missing ULE layout");var rejected=new Context();IntPtr unavailable=entry(ref rejected,new[]{Bits(Text(alloc,heap,strings,unlinked))});Check(unavailable==IntPtr.Zero&&rejected.Kind==16&&rejected.Pending!=0&&Marshal.ReadIntPtr(new IntPtr(unchecked((long)rejected.Pending)),-8)==uleTag,"Unlinked existing bootstrap target was silently treated as missing");
            // Successful, missing, invalid and null names remain allocation-free when warm.
            long before=Marshal.ReadInt64(heap,48);Parallel.For(0,8,worker=>{for(int j=0;j<256;j++){int i=j%cases.Length;Check(invoke(i)==results[i],"Parallel bootstrap lookup differs");}});Check(Marshal.ReadInt64(heap,48)==before,"Warm bootstrap lookup allocated guest objects");
            return results;
        } finally {if(image!=IntPtr.Zero&&GetProcAddress(image,"boom_release_trace_pool")!=IntPtr.Zero)Check(Fn<Release>(image,"boom_release_trace_pool")()==0,"Bootstrap frames remain");if(heap!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(heap);if(rt!=IntPtr.Zero)FreeLibrary(rt);if(image!=IntPtr.Zero)FreeLibrary(image);}
    }
}
