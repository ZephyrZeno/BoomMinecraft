// Runs original JDK Character bytecode compiled to MASM; this is a test host.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
public static class BoomCharacterProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Descriptor(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint id,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,uint type);
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static int Reachable(IntPtr roots,uint n){var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>();for(int i=0;i<n;i++)todo.Push(Marshal.ReadIntPtr(roots,i*8));while(todo.Count!=0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint f=unchecked((uint)Marshal.ReadInt32(p,-24)),refs=unchecked((uint)Marshal.ReadInt32(p,-20));long bytes=Marshal.ReadInt64(p,-16);Check((f&0xfffffffd)==0xb00b0001&&bytes>=0&&refs<=(ulong)bytes/8&&seen.Count<1048576,"Invalid original character graph");for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,i*8));}return seen.Count;}
    static void GC(IntPtr m,IntPtr h){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);int live=Reachable(roots,n);Check(Fn<Collect>(m,"boom_heap_collect")(h,roots,n)!=ulong.MaxValue&&Marshal.ReadInt64(h,56)==live,"Original character static roots lost");}
    static uint Read32(BinaryReader reader){uint a=reader.ReadByte(),b=reader.ReadByte(),c=reader.ReadByte(),d=reader.ReadByte();return a<<24|b<<16|c<<8|d;}
    static void Map(IntPtr array,int depth,BinaryReader reader){uint n=Read32(reader);Check(array!=IntPtr.Zero&&n<65536,"Invalid character map node");long bytes=Marshal.ReadInt64(array,-16);if(depth==1){Check(Marshal.ReadInt64(array,-8)==261&&Marshal.ReadInt32(array,-20)==0&&bytes==n*2,"Invalid original map char leaf");for(int i=0;i<n;i++){int expected=reader.ReadByte()*256+reader.ReadByte();Check(unchecked((ushort)Marshal.ReadInt16(array,i*2))==expected,"Original character map value mismatch");}}else{Check(bytes==n*8&&Marshal.ReadInt32(array,-20)==n,"Invalid original map reference layer");for(int i=0;i<n;i++)Map(Marshal.ReadIntPtr(array,i*8),depth-1,reader);}}
    static void MapCheck(IntPtr m,uint owner,uint field,byte[] expected){IntPtr cell=Fn<Field>(m,"boom_get_static_field")(owner,field);Check(cell!=IntPtr.Zero,"Missing original charMap field");using(var stream=new MemoryStream(expected))using(var reader=new BinaryReader(stream)){Map(Marshal.ReadIntPtr(cell),3,reader);Check(stream.Position==stream.Length,"Original character map length changed");}}
    static void Call(Entry e,ulong[] a,int cp,byte expected){a[0]=unchecked((uint)cp);var c=new Context();ulong value=e(ref c,a);Check(value==expected&&c.Kind==0&&c.Depth==0,"Original Character.getType mismatch at "+unchecked((uint)cp).ToString("x")+": value="+value+", kind="+c.Kind+", method="+c.Method+", pc="+c.PC);}
    public static void Run(string dll,string runtime,byte[] expected,uint[] ids,uint mapOwner,uint mapField,byte[] map){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),h=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Character module load failed");
        try{h=Fn<Create>(m,"boom_heap_create")(8*1024*1024);Check(h!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(h)==1&&expected.Length==0x110000+520,"Character heap/oracle setup failed");var e=Fn<Entry>(m,"boom_entry");var a=new ulong[1];
            foreach(uint id in ids)Check(Marshal.ReadInt32(Fn<Descriptor>(m,"boom_get_class_descriptor")(id),8)==0,"Character data was not initially cold");
            for(int cp=0;cp<0x110000;cp++){Call(e,a,cp,expected[cp]);if((cp&65535)==65535)GC(m,h);}
            int[] edge={-1,int.MinValue,int.MaxValue,0x110000,0x110001,0x3fffffff,0x7ffffffe,unchecked((int)0x80000001)};
            for(int i=0;i<8;i++)Call(e,a,edge[i],expected[0x110000+i]);int x=0x45004500;for(int i=0;i<512;i++){x=unchecked(x*1664525+1013904223);Call(e,a,x,expected[0x110008+i]);}
            foreach(uint id in ids)Check(Marshal.ReadInt32(Fn<Descriptor>(m,"boom_get_class_descriptor")(id),8)==2,"Original character class initializer did not complete");
            MapCheck(m,mapOwner,mapField,map);GC(m,h);MapCheck(m,mapOwner,mapField,map);
            for(int i=0;i<512;i++){int cp=(i*2177)%0x110000;Call(e,a,cp,expected[cp]);}
            GC(m,h);var alloc=Fn<Alloc>(r,"boom_heap_alloc");while(alloc(h,4096,0,267)!=IntPtr.Zero){}while(alloc(h,0,0,267)!=IntPtr.Zero){}long full=Marshal.ReadInt64(h,56);
            for(int i=0;i<8193;i++){int cp=(i*131)%0x110000;Call(e,a,cp,expected[cp]);Check(Marshal.ReadInt64(h,56)==full,"Warm character query allocated on full heap");}
            GC(m,h);MapCheck(m,mapOwner,mapField,map);
        }finally{IntPtr release=GetProcAddress(m,"boom_release_trace_pool");if(release!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<Release>(release)()==0,"Character Java frames active");if(h!=IntPtr.Zero)Check(Fn<Destroy>(m,"boom_heap_destroy")(h)!=0,"Character heap cleanup failed");FreeLibrary(m);FreeLibrary(r);}
    }
}
