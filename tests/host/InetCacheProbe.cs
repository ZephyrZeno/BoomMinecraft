// JNI-cache metadata ABI fixture. No InetAddress Java initialization or sockets.
using System;
using System.Runtime.InteropServices;
public static class BoomInetCacheProbe {
 [StructLayout(LayoutKind.Sequential)]struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
 [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
 [DllImport("kernel32.dll")]static extern uint GetCurrentThreadId();
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Init(ref Context c,IntPtr argv,IntPtr pool);
 static void Check(bool b,string m){if(!b)throw new Exception(m);}
 static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
 public static void RunFamily(string fixture,string runtime,string getter,int family){
  IntPtr m=LoadLibraryExW(fixture,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Inet family image load");
  IntPtr ctor=IntPtr.Zero,rows=IntPtr.Zero;
  try{
   IntPtr pool=Fn<Pointer>(m,getter)(),owner=Marshal.ReadIntPtr(pool,16),originalCtor=Marshal.ReadIntPtr(pool,64),originalRows=Marshal.ReadIntPtr(pool,56);
   var init=Fn<Init>(r,"boom_inet_address_init");var c=new Context();init(ref c,IntPtr.Zero,pool);Check(c.Kind==7,"Uninitialized family class accepted");
   Marshal.WriteInt32(owner,8,1);Marshal.WriteInt32(owner,12,unchecked((int)GetCurrentThreadId()+1));c=new Context();init(ref c,IntPtr.Zero,pool);Check(c.Kind==7,"Wrong family owner accepted");
   Marshal.WriteInt32(owner,12,unchecked((int)GetCurrentThreadId()));c=new Context();init(ref c,IntPtr.Zero,pool);Check(c.Kind==0&&Marshal.ReadInt32(pool,8)==2,"Family cache owner publication");
   Marshal.WriteInt32(owner,8,2);Marshal.WriteInt32(pool,8,0);
   System.Threading.Tasks.Parallel.For(0,8,worker=>{for(int i=0;i<128;i++){var local=new Context();init(ref local,IntPtr.Zero,pool);Check(local.Kind==0&&local.Depth==0,"Concurrent family metadata publication");}});Check(Marshal.ReadInt32(pool,8)==2,"Family metadata not published");
   Action<IntPtr,int,int> bad=(p,offset,value)=>{int saved=Marshal.ReadInt32(p,offset);Marshal.WriteInt32(p,offset,value);try{var x=new Context();init(ref x,IntPtr.Zero,pool);Check(x.Kind==7,"Malformed family metadata "+offset);}finally{Marshal.WriteInt32(p,offset,saved);}};
   bad(pool,0,0);bad(pool,4,0);bad(pool,8,1);bad(pool,12,3);bad(pool,72,9);bad(owner,4,1);bad(owner,8,3);
   ctor=Marshal.AllocHGlobal(32);byte[] bytes=new byte[32];Marshal.Copy(originalCtor,bytes,0,32);Marshal.Copy(bytes,0,ctor,32);Marshal.WriteIntPtr(pool,64,ctor);
   bad(ctor,0,0);bad(ctor,4,0);bad(ctor,8,0);bad(ctor,16,-1);bad(ctor,20,1);bad(ctor,24,1);
   if(family==6){rows=Marshal.AllocHGlobal(120);bytes=new byte[120];Marshal.Copy(originalRows,bytes,0,120);Marshal.Copy(bytes,0,rows,120);Marshal.WriteIntPtr(pool,56,rows);bad(rows,0,2);bad(rows,4,3);bad(rows,8,-1);bad(rows,20,2);}
   var pending=new Context{Kind=16,PC=3,Method=5,Depth=2,Pending=7,Plan=11};init(ref pending,IntPtr.Zero,IntPtr.Zero);Check(pending.Kind==16&&pending.PC==3&&pending.Method==5&&pending.Depth==2&&pending.Pending==7&&pending.Plan==11,"Pending family context changed");
   Marshal.WriteIntPtr(pool,64,originalCtor);Marshal.WriteIntPtr(pool,56,originalRows);c=new Context();init(ref c,IntPtr.Zero,pool);Check(c.Kind==0&&Marshal.ReadInt32(pool,8)==2,"Family cache did not recover");
  }finally{if(ctor!=IntPtr.Zero)Marshal.FreeHGlobal(ctor);if(rows!=IntPtr.Zero)Marshal.FreeHGlobal(rows);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
 }
 public static void Run(string fixture,string runtime){
  IntPtr m=LoadLibraryExW(fixture,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Inet cache DLL load failed");
  try{
   IntPtr pool=Fn<Pointer>(m,"boom_get_inet_cache")(),owner=Marshal.ReadIntPtr(pool,16);var init=Fn<Init>(r,"boom_inet_address_init");
   var c=new Context();Check(init(ref c,IntPtr.Zero,pool)==0&&c.Kind==7&&Marshal.ReadInt32(pool,8)==0,"Uninitialized InetAddress owner was accepted");
   Marshal.WriteInt32(owner,8,1);Marshal.WriteInt32(owner,12,unchecked((int)GetCurrentThreadId()+1));c=new Context();init(ref c,IntPtr.Zero,pool);Check(c.Kind==7&&Marshal.ReadInt32(pool,8)==0,"Foreign initializing thread accepted");
   Marshal.WriteInt32(owner,12,unchecked((int)GetCurrentThreadId()));c=new Context();Check(init(ref c,IntPtr.Zero,pool)==0&&c.Kind==0&&Marshal.ReadInt32(pool,8)==2,"Initializing owner failed to publish JNI cache");
   Marshal.WriteInt32(owner,8,2);Marshal.WriteInt32(owner,12,0);Marshal.WriteInt32(pool,8,0);
   System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int i=0;i<128;i++){var t=new Context();Check(init(ref t,IntPtr.Zero,pool)==0&&t.Kind==0&&t.Depth==0,"Concurrent metadata cache publication failed");}});Check(Marshal.ReadInt32(pool,8)==2,"Published cache state differs");
   var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(init(ref pending,IntPtr.Zero,IntPtr.Zero)==0&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending InetAddress context changed");
   Action<IntPtr,int,int> bad=(p,offset,value)=>{int saved=Marshal.ReadInt32(p,offset);Marshal.WriteInt32(p,offset,value);try{var x=new Context();init(ref x,IntPtr.Zero,pool);Check(x.Kind==7,"Malformed InetAddress metadata accepted at "+offset);}finally{Marshal.WriteInt32(p,offset,saved);}};
   bad(pool,0,0);bad(pool,4,2);bad(pool,8,1);bad(pool,12,4);bad(pool,64,1);bad(owner,0,0);bad(owner,4,1);bad(owner,8,3);
   IntPtr originalType=Marshal.ReadIntPtr(pool,24),originalLayout=Marshal.ReadIntPtr(pool,40),originalRows=Marshal.ReadIntPtr(pool,56);
   Func<IntPtr,int,IntPtr> copy=(p,n)=>{IntPtr result=Marshal.AllocHGlobal(n);byte[] bytes=new byte[n];Marshal.Copy(p,bytes,0,n);Marshal.Copy(bytes,0,result,n);return result;};
   IntPtr type=copy(originalType,40),layout=copy(originalLayout,24),rows=copy(originalRows,120);
   try{Marshal.WriteIntPtr(pool,24,type);Marshal.WriteIntPtr(pool,40,layout);Marshal.WriteIntPtr(pool,56,rows);
    bad(type,0,0);bad(type,4,2);bad(type,8,2);bad(layout,0,0);bad(layout,4,1);bad(layout,16,999999);bad(rows,0,2);bad(rows,4,4);bad(rows,8,-1);bad(rows,20,2);
   }finally{Marshal.WriteIntPtr(pool,24,originalType);Marshal.WriteIntPtr(pool,40,originalLayout);Marshal.WriteIntPtr(pool,56,originalRows);Marshal.FreeHGlobal(type);Marshal.FreeHGlobal(layout);Marshal.FreeHGlobal(rows);}
   c=new Context();init(ref c,IntPtr.Zero,pool);Check(c.Kind==0&&Marshal.ReadInt32(pool,8)==2,"InetAddress cache did not recover after restored metadata");
  }finally{if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
 }
}
