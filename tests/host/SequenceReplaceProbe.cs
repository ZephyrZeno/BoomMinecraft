// Full-DLL execution through frozen AOT CharSequence callbacks. Disposable host.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomSequenceReplaceProbe {
 [StructLayout(LayoutKind.Sequential)]struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
 [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Field(uint owner,uint field);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Entry(ref Context c,[In]ulong[] a);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Make(IntPtr h,IntPtr p,uint n,ref Context c);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Service(ref Context c,[In]ulong[] a,IntPtr h,IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Intrinsic(ref Context c,[In]ulong[] a,IntPtr p,uint operation);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
 static void Check(bool b,string s){if(!b)throw new Exception(s);}
 static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
 static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
 static string Text(IntPtr p){IntPtr data=Marshal.ReadIntPtr(p);return Marshal.PtrToStringUni(data,checked((int)(Marshal.ReadInt64(data,-16)/2)));}
 public static void Run(string dll,string runtime,uint planId,uint seqId,uint valueOffset,uint idOffset,uint modeOffset,uint owner,uint traceField,uint markerId,uint toStringMethod){
  IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Sequence runtime load failed");
  try{
   heap=Fn<Create>(r,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Sequence heap bind failed");
   var warm=new Context();Fn<Entry>(m,"boom_entry32")(ref warm,new[]{0UL,0UL,0UL,9UL});Check(warm.Kind==0,"Sequence warm entry failed");
   IntPtr plan=Fn<Indexed>(m,"boom_get_sequence_replace_plan")(planId),pool=Marshal.ReadIntPtr(plan,16),trace=Fn<Field>(m,"boom_get_static_field")(owner,traceField),layout=Fn<Indexed>(m,"boom_get_object_layout")(seqId),marker=Fn<Indexed>(m,"boom_get_object_layout")(markerId);
   Check(plan!=IntPtr.Zero&&Marshal.ReadInt32(plan,8)==2,"Sequence plan getter differs");var make=Fn<Make>(r,"boom_string_allocate");var alloc=Fn<Alloc>(r,"boom_heap_alloc");var query=Fn<Service>(r,"boom_string_replace_sequence");
   Func<string,IntPtr> str=value=>{var c=new Context();IntPtr p=make(heap,pool,(uint)value.Length,ref c);Check(c.Kind==0&&p!=IntPtr.Zero,"Sequence String fixture failed");IntPtr data=Marshal.ReadIntPtr(p);for(int i=0;i<value.Length;i++)Marshal.WriteInt16(data,i*2,unchecked((short)value[i]));return p;};
   Func<int,int,IntPtr,IntPtr> seq=(id,mode,value)=>{IntPtr p=alloc(heap,unchecked((ulong)Marshal.ReadInt64(layout,8)),unchecked((uint)Marshal.ReadInt32(layout,16)),Bits(layout));Check(p!=IntPtr.Zero,"Sequence object fixture failed");Marshal.WriteIntPtr(p,(int)valueOffset,value);Marshal.WriteInt32(p,(int)idOffset,id);Marshal.WriteInt32(p,(int)modeOffset,mode);return p;};
   foreach(string input in new[]{"","a","aaaaa","abaaba","x\n_\r\n","\ud801\udc00_\ud800\udc00","\ud800_\udc00","\0a_\0"})foreach(string old in new[]{"","a","aa","ab","\n","\ud800","\0"})foreach(string replacement in new[]{"","a","XYZ","\\n","\udc00"}){
    IntPtr before=str(input),target=seq(1,1,str(old)),next=seq(2,1,str(replacement));Marshal.WriteInt32(trace,0);var c=new Context{Plan=warm.Plan};IntPtr after=query(ref c,new[]{Bits(before),Bits(target),Bits(next)},heap,plan);
    var encoding=new Context{Plan=warm.Plan};Check(Fn<Intrinsic>(r,"boom_string_intrinsic")(ref encoding,new[]{Bits(before)},pool,23).ToInt64()==1&&encoding.Kind==0,"VM UTF16 coder property differs");
    string expected;if(old.Length==0){var sb=new System.Text.StringBuilder(replacement);foreach(char x in input){sb.Append(x);sb.Append(replacement);}expected=sb.ToString();}else expected=input.Replace(old,replacement);
    Check(c.Kind==0&&c.Depth==0&&after!=IntPtr.Zero&&Text(after)==expected&&Marshal.ReadInt32(trace)==12,"Packaged sequence content/callback differs");bool same=(old.Length==1&&replacement.Length==1&&old==replacement)||(old.Length>0&&!input.Contains(old,StringComparison.Ordinal));Check((after==before)==same,"Packaged sequence result identity differs");
   }
   IntPtr source=str("abaaba"),patt=str("ab"),repl=str("XYZ"),left=seq(1,3,patt),right=seq(2,1,repl);Marshal.WriteInt32(trace,0);var fail=new Context{Plan=warm.Plan};query(ref fail,new[]{Bits(source),Bits(left),Bits(right)},heap,plan);Check(fail.Kind==4&&Marshal.ReadInt32(trace)==12,"Null-return callback skipped replacement callback");
   left=seq(1,2,patt);Marshal.WriteInt32(trace,0);fail=new Context{Plan=warm.Plan};query(ref fail,new[]{Bits(source),Bits(left),Bits(right)},heap,plan);Check(fail.Kind==16&&fail.Pending!=0&&fail.Depth==0&&fail.Method==toStringMethod&&Marshal.ReadInt32(trace)==1&&Marshal.ReadIntPtr(new IntPtr(unchecked((long)fail.Pending)),-8)==marker,"Callback Throwable/source was replaced");
   var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(query(ref pending,null,IntPtr.Zero,IntPtr.Zero)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending sequence context changed");
   var parallel=new IntPtr[1024];System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int i=0;i<128;i++){var c=new Context{Plan=warm.Plan};IntPtr p=query(ref c,new[]{Bits(source),Bits(patt),Bits(repl)},heap,plan);Check(c.Kind==0&&c.Depth==0&&Text(p)=="XYZaXYZa","Concurrent sequence output differs");parallel[worker*128+i]=p;}});
   Check(new HashSet<IntPtr>(parallel).Count==1024,"Concurrent sequence instances shared");
   IntPtr plain=str("plain"),missing=str("z"),more=str("zz");var keep=new[]{source,patt,repl,plain,missing,more};
   Action collect=()=>{IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+keep.Length)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<keep.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,keep[i]);Check(Fn<Collect>(r,"boom_heap_collect")(heap,all,n+(uint)keep.Length)!=ulong.MaxValue,"Sequence collection failed");}finally{Marshal.FreeHGlobal(all);}};
   collect();while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}
   for(int i=0;i<1024;i++){var c=new Context{Plan=warm.Plan};Check(query(ref c,new[]{Bits(plain),Bits(missing),Bits(more)},heap,plan)==plain&&c.Kind==0,"Full heap no-match sequence allocated");}
   fail=new Context{Plan=warm.Plan};Check(query(ref fail,new[]{Bits(source),Bits(patt),Bits(repl)},heap,plan)==IntPtr.Zero&&fail.Kind==3,"Full heap sequence OOM differs");collect();fail=new Context{Plan=warm.Plan};IntPtr recovered=query(ref fail,new[]{Bits(source),Bits(patt),Bits(repl)},heap,plan);Check(fail.Kind==0&&Text(recovered)=="XYZaXYZa","Sequence failed after explicit reclamation");
  }finally{if(m!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Sequence Java frames remain");if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
 }
}
