// Executes original locked StringConcatHelper.mix and checkOverflow in AOT ASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomCoderProbe {
 [StructLayout(LayoutKind.Sequential)]struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
 [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Entry(ref Context c,[In]ulong[] a);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
 static void Check(bool b,string s){if(!b)throw new Exception(s);}
 static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
 static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
 public static string[] Run(string dll,string runtime,string[] cases,uint[] ids,string[] names,uint messageOffset,uint overflowMethod){
  IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Coder image load failed");
  try{
   heap=Fn<Create>(r,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Coder heap bind failed");var entry=Fn<Entry>(m,"boom_entry32");var warm=new Context();entry(ref warm,new[]{0UL,0UL});Check(warm.Kind==16&&warm.Pending!=0&&warm.Depth==0,"Coder null receiver was not materialized");
   IntPtr anchor=Marshal.ReadIntPtr(new IntPtr(unchecked((long)warm.Pending)),(int)messageOffset);
   if(anchor==IntPtr.Zero){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint count);for(int i=0;i<count;i++){IntPtr p=Marshal.ReadIntPtr(roots,i*8);if(p==IntPtr.Zero||Marshal.ReadInt64(p,-16)!=16||Marshal.ReadInt32(p,-20)!=1)continue;IntPtr chars=Marshal.ReadIntPtr(p);if(chars!=IntPtr.Zero&&Marshal.ReadIntPtr(chars,-8).ToInt64()==261){anchor=p;break;}}}
   Check(anchor!=IntPtr.Zero&&Marshal.ReadInt64(anchor,-16)==16,"Coder String-tag fixture missing");ulong tag=Bits(Marshal.ReadIntPtr(anchor,-8));var alloc=Fn<Alloc>(r,"boom_heap_alloc");var layout=Fn<Indexed>(m,"boom_get_object_layout");var typeNames=new Dictionary<IntPtr,string>();for(int i=0;i<ids.Length;i++)typeNames[layout(ids[i])]=names[i];var results=new List<string>();
   foreach(string line in cases){string[] parts=line.Split(new[]{' '},2);ulong value=Convert.ToUInt64(parts[0],16);IntPtr text=IntPtr.Zero;if(parts[1]!="null"){string[] units=parts[1].Length==0?Array.Empty<string>():parts[1].Split(':');IntPtr chars=alloc(heap,(ulong)units.Length*2,0,261);Check(chars!=IntPtr.Zero,"Coder char fixture failed");for(int i=0;i<units.Length;i++)Marshal.WriteInt16(chars,i*2,unchecked((short)Convert.ToUInt16(units[i],16)));text=alloc(heap,16,1,tag);Check(text!=IntPtr.Zero,"Coder String fixture failed");Marshal.WriteIntPtr(text,chars);}
    var c=new Context();ulong result=entry(ref c,new[]{value,Bits(text)});Check(c.Depth==0,"Coder Java frame leaked");if(c.Kind==0)results.Add("v "+result.ToString("x16"));else{Check(c.Kind==16&&c.Pending!=0,"Unmaterialized coder exception");string name=typeNames[Marshal.ReadIntPtr(new IntPtr(unchecked((long)c.Pending)),-8)];if(name=="java.lang.OutOfMemoryError")Check(c.Method==overflowMethod,"Original overflow Java source changed");results.Add("e "+name);}
   }return results.ToArray();
  }finally{if(m!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Coder frames remain");if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
 }
}
