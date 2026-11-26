package dev.boom.sequence;
public final class SequenceProgram {
 public static int trace;
 public static final class Marker extends RuntimeException {public final int value;public Marker(int value){this.value=value;}}
 public static final class Seq implements CharSequence {
  final int id,mode;final String value;
  public Seq(int id,int mode,String value){this.id=id;this.mode=mode;this.value=value;}
  public String toString(){trace=trace*10+id;if(mode==2)throw new Marker(id);return mode==3?null:value;}
  public int length(){return value.length();}public char charAt(int i){return value.charAt(i);}public CharSequence subSequence(int a,int b){return value.substring(a,b);}
 }
 public static String text(int i){return switch(i){case 0->"";case 1->"a";case 2->"b";case 3->"aa";case 4->"aaa";case 5->"aaaaa";case 6->"abaaba";case 7->"x\n_\r\n";case 8->"\\n";case 9->"\ud801\udc00";case 10->"\ud800";case 11->"\udc00";case 12->"\u0000a_\u0000";default->"_XYZ_";};}
 public static CharSequence seq(int kind,int value,int id){return kind==4?null:kind==0?text(value):new Seq(id,kind,text(value));}
 public static int run(int s,int t,int r,int mode){
  trace=0;String before=s<0?null:text(s);CharSequence target=seq(mode&7,t,1),replacement=(mode&256)!=0?target:seq((mode>>3)&7,r,2);
  try{String after=before.replace(target,replacement);return switch((mode>>6)&3){case 0->after.length();case 1->after.hashCode();case 2->after==before?1:0;default->trace;};}
  catch(Marker e){return -100000-trace*10-e.value;}catch(NullPointerException e){return -200000-trace;}
 }
 public static int raw(int x,int y,int old,int replacement){String input=new String(new char[]{(char)x,'_',(char)y,(char)x,'A'});String target=new String(new char[]{(char)old});String next=new String(new char[]{(char)replacement,'X'});return input.replace(target,next).hashCode();}
}
