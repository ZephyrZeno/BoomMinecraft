package dev.boom.literalregex;
public final class LiteralProgram {
 public static String text(int kind){return switch(kind){case 0->"";case 1->"a_b_c";case 2->"a-b-c";case 3->"_____";case 4->"plain";case 5->"Aa\u0000_B";case 6->"\u03a3_\u03c3";case 7->"\ud801\udc00_\ud800\udc00";case 8->"\ud800_\udc00";case 9->"aaabaaa";case 10->"a\na\u0000_";default->"a-b_\u03a3";};}
 public static String change(String s,int route){return switch(route){case 0->s.replaceAll("_","-");case 1->s.replaceAll("-","_");case 2->s.replaceAll("a","b");case 3->s.replaceAll("\u03a3","\u03c3");case 4->s.replaceAll("\u0000","x");case 5->s.replaceAll("a","\ud800");case 6->s.replaceAll("\n","\u0000");case 7->s.replaceAll("_","^");default->Wide.change(s);};}
 public static int run(int a,int route,int operation){
  String before=operation==3?new String(new char[]{(char)a,'_','a','\ud800','\udc00','\n','_'}):a<0?null:text(a);
  try {String after=change(before,route);return operation==0?after.length():operation==2?(after==before?1:0):after.hashCode();}catch(NullPointerException e){return -1;}
 }
 public static String badMeta(String s){return s.replaceAll(".","-");}
 public static String badIdentity(String s){return s.replaceAll("_","_");}
 public static String badSurrogate(String s){return s.replaceAll("\ud800","x");}
 public static String badReplacement(String s){return s.replaceAll("_","$");}
 public static String badEmpty(String s){return s.replaceAll("","-");}
 public static String badDynamic(String s,String pattern){return s.replaceAll(pattern,"-");}
 public static String badBranch(String s,boolean which){return s.replaceAll(which?"_":"-","?");}
}
