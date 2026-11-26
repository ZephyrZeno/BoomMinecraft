// Disposable differential controller. Game execution remains in generated/handwritten ASM.
using System;
using System.IO;
using System.Globalization;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomConstructorProbe {
 [StructLayout(LayoutKind.Sequential)] public struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
 [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Indexed(uint id);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint owner,uint field);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr h,IntPtr pool,uint id,ref Context c);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In]ulong[] a);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Service(ref Context c,[In]ulong[] a,IntPtr p,uint operation);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
 static void Check(bool v,string why) {if(!v)throw new Exception(why);}
 static T Fn<T>(IntPtr m,string name) {IntPtr p=GetProcAddress(m,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
 static ulong Bits(IntPtr p) {return unchecked((ulong)p.ToInt64());}
 static string Text(IntPtr value) {if(value==IntPtr.Zero)return "<null>";IntPtr data=Marshal.ReadIntPtr(value);return Marshal.PtrToStringUni(data,checked((int)(Marshal.ReadInt64(data,-16)/2)));}
 sealed class Image:IDisposable {
  public IntPtr Module,Heap,Pool,ArgumentLayout; public string[] Names; public uint[] BoxOffsets; public Entry Invoke; public Alloc Allocate; public Load Mirror,String;
  Dictionary<string,uint> typeIds=new Dictionary<string,uint>(); Dictionary<IntPtr,string> objectNames=new Dictionary<IntPtr,string>(); Dictionary<string,uint> scores=new Dictionary<string,uint>();
  public Image(string path,string[] names,uint[] ids,string[] layouts,uint[] offsets,uint[] boxed) {
   Names=names;BoxOffsets=boxed;Module=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(Module!=IntPtr.Zero,"Constructor image load failed");
   Heap=Fn<Create>(Module,"boom_heap_create")(16777216);Check(Heap!=IntPtr.Zero&&Fn<One>(Module,"boom_bind_heap")(Heap)==1,"Constructor heap bind failed");
   Pool=Fn<Pointer>(Module,"boom_get_constructor_pool")();ArgumentLayout=Fn<Pointer>(Module,"boom_get_constructor_argument_layout")();
   Invoke=Fn<Entry>(Module,"boom_entry32");Allocate=Fn<Alloc>(Module,"boom_heap_alloc");Mirror=Fn<Load>(Module,"boom_mirror_load");String=Fn<Load>(Module,"boom_string_allocate");
   for(uint i=0;i<names.Length;i++)typeIds[names[i]]=i;
   var layout=Fn<Indexed>(Module,"boom_get_object_layout");for(int i=0;i<ids.Length;i++){objectNames[layout(ids[i])]=layouts[i];scores[layouts[i]]=offsets[i];}
  }
  public void Dispose(){if(Module!=IntPtr.Zero){Check(Fn<Release>(Module,"boom_release_trace_pool")()==0,"Reflective Java frames remain");if(Heap!=IntPtr.Zero)Fn<One>(Module,"boom_heap_destroy")(Heap);FreeLibrary(Module);}}
  public IntPtr Array(IntPtr[] values,IntPtr tag) {IntPtr p=Allocate(Heap,(ulong)values.Length*8,(uint)values.Length,Bits(tag));Check(p!=IntPtr.Zero,"Array fixture allocation failed");for(int i=0;i<values.Length;i++)Marshal.WriteIntPtr(p,i*8,values[i]);return p;}
  public IntPtr Parameters(string text) {if(text=="null")return IntPtr.Zero;string[] parts=text.Length==0?System.Array.Empty<string>():text.Split(';');var result=new IntPtr[parts.Length];for(int i=0;i<parts.Length;i++){if(parts[i]=="null")continue;Check(typeIds.ContainsKey(parts[i]),"Missing mirror "+parts[i]);var c=new Context();result[i]=Mirror(Heap,Marshal.ReadIntPtr(Pool,16),typeIds[parts[i]],ref c);Check(c.Kind==0&&result[i]!=IntPtr.Zero,"Class fixture failed "+parts[i]);}return Array(result,Marshal.ReadIntPtr(Pool,88));}
  public IntPtr Argument(string text) {
   if(text=="N")return IntPtr.Zero;
   if(text=="obj"){var c=new Context();IntPtr p=Call(1,14,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref c);Check(c.Kind==0,"Object fixture constructor failed");return p;}
   int sep=text.IndexOf(':');Check(sep>0,"Bad argument fixture "+text);string kind=text.Substring(0,sep),value=text.Substring(sep+1);
   if(kind=="txt"){var c=new Context();IntPtr p=String(Heap,Marshal.ReadIntPtr(Pool,24),(uint)value.Length,ref c);Check(c.Kind==0&&p!=IntPtr.Zero,"String fixture failed");IntPtr data=Marshal.ReadIntPtr(p);for(int i=0;i<value.Length;i++)Marshal.WriteInt16(data,i*2,unchecked((short)value[i]));return p;}
   if(kind=="ints"){uint count=uint.Parse(value,CultureInfo.InvariantCulture);IntPtr p=Allocate(Heap,count*4UL,0,266);Check(p!=IntPtr.Zero,"int[] fixture failed");return p;}
   int k="ZBCSIJFD".IndexOf(kind,StringComparison.Ordinal);Check(k>=0,"Unknown boxed fixture "+kind);IntPtr tag=Fn<Indexed>(Module,"boom_get_constructor_box_layout")((uint)k);IntPtr box=Allocate(Heap,unchecked((ulong)Marshal.ReadInt64(tag,8)),0,Bits(tag));Check(box!=IntPtr.Zero,"Box fixture failed");
   long bits=kind=="Z"?(bool.Parse(value)?1L:0L):kind=="F"?BitConverter.SingleToInt32Bits(float.Parse(value,CultureInfo.InvariantCulture)):kind=="D"?BitConverter.DoubleToInt64Bits(double.Parse(value,CultureInfo.InvariantCulture)):long.Parse(value,CultureInfo.InvariantCulture);
   int at=(int)BoxOffsets[k];if(k<=1)Marshal.WriteByte(box,at,unchecked((byte)bits));else if(k<=3)Marshal.WriteInt16(box,at,unchecked((short)bits));else if(k==4||k==6)Marshal.WriteInt32(box,at,unchecked((int)bits));else Marshal.WriteInt64(box,at,bits);return box;
  }
  public IntPtr Arguments(string text){if(text=="null")return IntPtr.Zero;string[] parts=text.Length==0?System.Array.Empty<string>():text.Split(';');var args=new IntPtr[parts.Length];for(int i=0;i<parts.Length;i++)args[i]=Argument(parts[i]);return Array(args,ArgumentLayout);}
  public IntPtr Call(uint op,uint kind,IntPtr parameters,IntPtr args,bool outside,IntPtr ctor,ref Context c) {IntPtr result=Invoke(ref c,new[]{(ulong)op,(ulong)kind,Bits(parameters),Bits(args),outside?1UL:0UL,Bits(ctor)});Check(c.Depth==0,"Leaked reflection frame "+op+"/"+c.Kind);return result;}
  public string Name(IntPtr value){Check(value!=IntPtr.Zero,"Missing object");IntPtr tag=Marshal.ReadIntPtr(value,-8);Check(objectNames.ContainsKey(tag),"Unknown reflection result tag "+tag);return objectNames[tag];}
  string Classes(IntPtr array){int n=Marshal.ReadInt32(array,-20);var values=new string[n];for(int i=0;i<n;i++)values[i]=Names[checked((int)Marshal.ReadInt64(Marshal.ReadIntPtr(array,i*8)))];return string.Join(",",values);}
  public string Describe(IntPtr value) {
   if(Marshal.ReadIntPtr(value,-8)==Marshal.ReadIntPtr(Pool,40)){
    var c=new Context();IntPtr parameters=Call(4,0,IntPtr.Zero,IntPtr.Zero,false,value,ref c);Check(c.Kind==0,"Constructor parameter getter failed");
    c=new Context();IntPtr exceptions=Call(5,0,IntPtr.Zero,IntPtr.Zero,false,value,ref c);Check(c.Kind==0,"Constructor exception getter failed");
    c=new Context();IntPtr name=Call(6,0,IntPtr.Zero,IntPtr.Zero,false,value,ref c);Check(c.Kind==0,"Constructor name getter failed");
    c=new Context();IntPtr flags=Call(8,0,IntPtr.Zero,IntPtr.Zero,false,value,ref c);Check(c.Kind==0,"Constructor flags getter failed");
    return "ctor:"+Text(name)+"("+Classes(parameters)+"):"+Marshal.ReadInt32(flags)+":"+Marshal.ReadInt32(flags,4)+":"+Marshal.ReadInt32(flags,8)+":"+Marshal.ReadInt32(flags,12)+":"+Marshal.ReadInt32(flags,16)+":"+Classes(exceptions);
   }
   string type=Name(value);long score=scores[type]==uint.MaxValue?0:Marshal.ReadInt64(value,(int)scores[type]);return "value:"+type+":"+score;
  }
  public string Error(Context c,uint causeOffset) {Check(c.Kind==16&&c.Pending!=0,"Unmaterialized constructor error: "+c.Kind+" at "+c.Method+"/"+c.PC);IntPtr error=new IntPtr(unchecked((long)c.Pending));string type=Name(error);IntPtr cause=Marshal.ReadIntPtr(error,(int)(type=="java.lang.reflect.InvocationTargetException"?(uint)Marshal.ReadInt32(Pool,124):causeOffset));string causeName=cause==IntPtr.Zero||cause==error?"-":Name(cause);string message=type=="java.lang.NoSuchMethodException"?Text(Marshal.ReadIntPtr(error,Marshal.ReadInt32(Pool,120))):"-";return "error:"+type+":"+causeName+":"+message;}
  public void Collect(params IntPtr[] extra){IntPtr roots=Fn<Roots>(Module,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);Check(Fn<Collect>(Module,"boom_heap_collect")(Heap,all,n+(uint)extra.Length)!=ulong.MaxValue,"Reflection collection failed");}finally{Marshal.FreeHGlobal(all);}}
 }
 public static string[] Run(string dll,string path,string[] typeNames,uint[] ids,string[] layoutNames,uint[] scoreOffsets,uint[] boxOffsets,uint causeOffset,uint counterOwner,uint counterField) {
  using(var image=new Image(dll,typeNames,ids,layoutNames,scoreOffsets,boxOffsets)) {
   var results=new List<string>();IntPtr first=IntPtr.Zero;
   foreach(string line in File.ReadAllLines(path)){string[] row=line.Split('|');IntPtr parameters=image.Parameters(row[3]),args=image.Arguments(row[4]);var c=new Context();IntPtr value=image.Call(uint.Parse(row[1]),uint.Parse(row[2]),parameters,args,row[5]=="1",IntPtr.Zero,ref c);string result=c.Kind==0?image.Describe(value):image.Error(c,causeOffset);results.Add(row[0]+" "+result);
    if(row[0]=="lookup-0"){first=value;Check(Marshal.ReadInt32(Fn<Field>(image.Module,"boom_get_static_field")(counterOwner,counterField))==0,"Constructor lookup initialized Target");}
    image.Collect(first,c.Kind==0?value:new IntPtr(unchecked((long)c.Pending)));
   }
   var copy=new Context();IntPtr second=image.Call(0,0,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref copy);Check(copy.Kind==0&&second!=first,"Constructor copies share identity");
   var a=new Context();IntPtr types=image.Call(4,0,IntPtr.Zero,IntPtr.Zero,false,first,ref a);a=new Context();IntPtr more=image.Call(4,0,IntPtr.Zero,IntPtr.Zero,false,first,ref a);Check(a.Kind==0&&types!=more,"Empty parameter arrays were not copied");
   a=new Context();IntPtr eq=image.Call(8,0,IntPtr.Zero,image.Array(new[]{second},image.ArgumentLayout),false,first,ref a);Check(a.Kind==0&&Marshal.ReadInt32(eq,20)==1,"Constructor equality lost metadata identity");
   // A cold independent image is required to exercise initializer contention.
   return results.ToArray();
  }
 }
 public static void Edges(string dll,string[] names,uint[] ids,string[] layouts,uint[] offsets,uint[] boxed,uint causeOffset){
  using(var image=new Image(dll,names,ids,layouts,offsets,boxed)){
   var service=Fn<Service>(image.Module,"boom_constructor_service");var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};
   Check(service(ref pending,null,IntPtr.Zero,99)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending Constructor context changed");
   var c=new Context();IntPtr ctor=image.Call(0,0,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref c);Check(c.Kind==0,"Edge constructor lookup failed");
   c=new Context();IntPtr target=image.Call(2,0,IntPtr.Zero,IntPtr.Zero,false,ctor,ref c);Check(c.Kind==0&&image.Describe(target).EndsWith(":42",StringComparison.Ordinal),"Edge constructor initialization failed");
   c=new Context();image.Call(2,0,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref c);Check(image.Error(c,causeOffset).StartsWith("error:java.lang.NullPointerException:",StringComparison.Ordinal),"Null Constructor receiver accepted");
   IntPtr fake=image.Allocate(image.Heap,32,1,Bits(Marshal.ReadIntPtr(image.Pool,40)));Check(fake!=IntPtr.Zero,"Bad Constructor fixture allocation failed");
   for(int i=0;i<4;i++)Marshal.WriteInt64(fake,i*8,Marshal.ReadInt64(ctor,i*8));
   foreach(int field in new[]{8,16,24}){
    long saved=Marshal.ReadInt64(fake,field);Marshal.WriteInt64(fake,field,field==8?saved+1:field==16?0:1);c=new Context();image.Call(2,0,IntPtr.Zero,IntPtr.Zero,false,fake,ref c);Check(image.Error(c,causeOffset).StartsWith("error:java.lang.VerifyError:",StringComparison.Ordinal),"Malformed Constructor field accepted "+field);Marshal.WriteInt64(fake,field,saved);
   }
   IntPtr foreign=Fn<Create>(image.Module,"boom_heap_create")(4096);
   try {IntPtr foreignCtor=image.Allocate(foreign,32,1,Bits(Marshal.ReadIntPtr(image.Pool,40)));for(int i=0;i<4;i++)Marshal.WriteInt64(foreignCtor,i*8,Marshal.ReadInt64(ctor,i*8));c=new Context();image.Call(2,0,IntPtr.Zero,IntPtr.Zero,false,foreignCtor,ref c);Check(image.Error(c,causeOffset).StartsWith("error:java.lang.VerifyError:",StringComparison.Ordinal),"Foreign heap Constructor accepted");}finally{Fn<One>(image.Module,"boom_heap_destroy")(foreign);}
   c=new Context();IntPtr stringCtor=image.Call(0,12,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref c);Check(c.Kind==0,"Unlinked String metadata lookup failed");c=new Context();image.Call(2,0,IntPtr.Zero,IntPtr.Zero,false,stringCtor,ref c);Check(image.Error(c,causeOffset).StartsWith("error:java.lang.UnsatisfiedLinkError:",StringComparison.Ordinal),"Unlinked String constructor was silently simulated");
   image.Collect(ctor,target);while(image.Allocate(image.Heap,4096,0,267)!=IntPtr.Zero){}while(image.Allocate(image.Heap,0,0,267)!=IntPtr.Zero){}
   c=new Context();image.Call(2,0,IntPtr.Zero,IntPtr.Zero,false,ctor,ref c);Check(image.Error(c,causeOffset).StartsWith("error:java.lang.OutOfMemoryError:",StringComparison.Ordinal),"Reflective allocation OOM was wrapped or lost");
   image.Collect(ctor,target);c=new Context();IntPtr recovered=image.Call(2,0,IntPtr.Zero,IntPtr.Zero,false,ctor,ref c);Check(c.Kind==0&&image.Describe(recovered).EndsWith(":42",StringComparison.Ordinal),"Reflection failed after explicit reclamation");
  }
 }
 public static void Packaged(string dll,string runtime,string[] names,uint[] ids,string[] layouts,uint[] offsets,uint[] boxed,uint causeOffset,uint caller){
  IntPtr module=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);Check(module!=IntPtr.Zero,"Packaged Constructor runtime load failed");
  IntPtr site=Marshal.AllocHGlobal(32),access=IntPtr.Zero;
  try{using(var image=new Image(dll,names,ids,layouts,offsets,boxed)){
   int rows=Marshal.ReadInt32(image.Pool,56);access=Marshal.AllocHGlobal(rows);for(int i=0;i<rows;i++)Marshal.WriteByte(access,i,0);
   Marshal.WriteInt32(site,0,0x50534343);Marshal.WriteInt32(site,4,1);Marshal.WriteIntPtr(site,8,image.Pool);Marshal.WriteIntPtr(site,16,access);Marshal.WriteInt32(site,24,unchecked((int)caller));Marshal.WriteInt32(site,28,0);
   var query=Fn<Service>(module,"boom_constructor_service");var warm=new Context();IntPtr ctor=image.Call(0,0,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref warm);Check(warm.Kind==0,"Packaged Constructor warm lookup failed");
   IntPtr mirror=Marshal.ReadIntPtr(ctor);var c=new Context{Plan=warm.Plan};IntPtr copy=query(ref c,new[]{Bits(mirror),0UL},site,0);Check(c.Kind==0&&copy!=IntPtr.Zero&&copy!=ctor&&image.Describe(copy)==image.Describe(ctor),"Packaged Constructor lookup differs");
   Marshal.WriteInt32(site,28,2);c=new Context{Plan=warm.Plan};IntPtr value=query(ref c,new[]{Bits(copy),0UL},site,2);Check(c.Kind==0&&image.Describe(value).EndsWith(":42",StringComparison.Ordinal),"Packaged original Java constructor differs");
   c=new Context();IntPtr throwing=image.Call(0,3,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref c);Check(c.Kind==0,"Packaged throwing constructor lookup failed");c=new Context{Plan=warm.Plan};query(ref c,new[]{Bits(throwing),0UL},site,2);Check(image.Error(c,causeOffset)=="error:java.lang.reflect.InvocationTargetException:dev.boom.constructors.CtorProgram$Marker:-","Packaged Constructor exception wrapping differs");
   IntPtr error=new IntPtr(unchecked((long)c.Pending));image.Collect(copy,value,error);Check(image.Describe(value).EndsWith(":42",StringComparison.Ordinal)&&image.Name(error)=="java.lang.reflect.InvocationTargetException","Packaged reflective graph was lost");
  }}finally{if(access!=IntPtr.Zero)Marshal.FreeHGlobal(access);Marshal.FreeHGlobal(site);FreeLibrary(module);}
 }
 public static void Parallel(string dll,string[] names,uint[] ids,string[] layouts,uint[] offsets,uint[] boxed,uint counterOwner,uint counterField){
  using(var image=new Image(dll,names,ids,layouts,offsets,boxed)){
   var values=new IntPtr[1024];System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int j=0;j<128;j++){var c=new Context();IntPtr p=image.Call(1,0,IntPtr.Zero,IntPtr.Zero,false,IntPtr.Zero,ref c);Check(c.Kind==0&&image.Describe(p).EndsWith(":42",StringComparison.Ordinal),"Concurrent reflective construction failed "+c.Kind);values[worker*128+j]=p;}});
   Check(new HashSet<IntPtr>(values).Count==values.Length,"Concurrent constructors shared instances");Check(Marshal.ReadInt32(Fn<Field>(image.Module,"boom_get_static_field")(counterOwner,counterField))==1,"Concurrent constructor initialized target more than once");image.Collect(values);foreach(IntPtr p in values)Check(image.Describe(p).EndsWith(":42",StringComparison.Ordinal),"Collected live reflection result");
  }
 }
}
