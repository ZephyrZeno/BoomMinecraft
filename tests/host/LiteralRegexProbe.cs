// Full-DLL ABI checks for the compiler-proven literal replacement adapter.
using System;
using System.Runtime.InteropServices;
public static class BoomLiteralRegexProbe {
 [StructLayout(LayoutKind.Sequential)]struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
 [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Entry(ref Context c,[In]ulong[] a);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Make(IntPtr h,IntPtr p,uint n,ref Context c);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Service(ref Context c,[In]ulong[] a,IntPtr p,uint chars);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
 static void Check(bool value,string message){if(!value)throw new Exception(message);}
 static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
 static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
 static string Text(IntPtr p){IntPtr data=Marshal.ReadIntPtr(p);return Marshal.PtrToStringUni(data,checked((int)(Marshal.ReadInt64(data,-16)/2)));}
 public static void Run(string dll,string runtime){
  IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Literal replacement DLL load failed");
  try{
   heap=Fn<Create>(r,"boom_heap_create")(8388608);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Literal replacement heap bind failed");
   var warm=new Context();Fn<Entry>(m,"boom_entry32")(ref warm,new[]{0UL,0UL,0UL});Check(warm.Kind==0,"Literal replacement warm entry failed");IntPtr pool=Fn<Pointer>(m,"boom_get_replace_string_pool")();var make=Fn<Make>(r,"boom_string_allocate");var query=Fn<Service>(r,"boom_string_replace_literal_chars");
   IntPtr plain=IntPtr.Zero,match=IntPtr.Zero;
   foreach(string input in new[]{"","plain","_","a_b_","\ud801\udc00_","\ud800_\udc00","\0_a"}){
    var c=new Context();IntPtr p=make(heap,pool,(uint)input.Length,ref c);Check(c.Kind==0&&p!=IntPtr.Zero,"Literal input fixture failed");IntPtr data=Marshal.ReadIntPtr(p);for(int i=0;i<input.Length;i++)Marshal.WriteInt16(data,i*2,unchecked((short)input[i]));
    c=new Context{Plan=warm.Plan};IntPtr result=query(ref c,new[]{Bits(p),0UL,0UL},pool,95U|(45U<<16));Check(c.Kind==0&&result!=IntPtr.Zero&&Text(result)==input.Replace('_','-'),"Full-DLL literal output differs");Check((result==p)==!input.Contains('_'),"Full-DLL literal identity differs");
    if(input=="plain")plain=p;if(input=="_")match=p;
   }
   var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(query(ref pending,null,IntPtr.Zero,0)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending literal context changed");
   var empty=new Context{Plan=warm.Plan};Check(query(ref empty,null,pool,0)==IntPtr.Zero&&empty.Kind==7,"Null argv accepted");empty=new Context{Plan=warm.Plan};Check(query(ref empty,new[]{0UL,0UL,0UL},pool,95U|(45U<<16))==IntPtr.Zero&&empty.Kind==4,"Null receiver accepted");
   var alloc=Fn<Alloc>(r,"boom_heap_alloc");while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}
   for(int i=0;i<1024;i++){var c=new Context{Plan=warm.Plan};Check(query(ref c,new[]{Bits(plain),0UL,0UL},pool,95U|(45U<<16))==plain&&c.Kind==0,"Full-heap no-match replacement allocated");}
   empty=new Context{Plan=warm.Plan};Check(query(ref empty,new[]{Bits(match),0UL,0UL},pool,95U|(45U<<16))==IntPtr.Zero&&empty.Kind==3,"Full-heap literal OOM differs");
   IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+2)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));Marshal.WriteIntPtr(all,(int)n*8,plain);Marshal.WriteIntPtr(all,((int)n+1)*8,match);Check(Fn<Collect>(r,"boom_heap_collect")(heap,all,n+2)!=ulong.MaxValue,"Literal explicit reclamation failed");}finally{Marshal.FreeHGlobal(all);}
   empty=new Context{Plan=warm.Plan};IntPtr recovered=query(ref empty,new[]{Bits(match),0UL,0UL},pool,95U|(45U<<16));Check(empty.Kind==0&&Text(recovered)=="-","Literal replacement failed after explicit GC");
  }finally{if(m!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Literal frames remain");if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
 }
}
