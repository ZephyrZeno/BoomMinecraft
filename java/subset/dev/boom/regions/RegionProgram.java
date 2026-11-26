package dev.boom.regions;
public final class RegionProgram {
 public static String text(int kind){return switch(kind){case 0->"";case 1->"jar";case 2->"JAR";case 3->"xjar:";case 4->"xJAR:";case 5->"\u03a3\u03c3\u03c2";case 6->"\u0130i\u0131I";case 7->"\u00df\u1e9e";case 8->"\u212aKk";case 9->"\ud801\udc00";case 10->"\ud801\udc28";case 11->"\ud800";case 12->"\udc00";case 13->"\ud800\udc00";case 14->"a\u0000B";default->"A\u0000b";};}
 public static int run(int a,int b,int offset,int otherOffset,int length,int mode){
  String left=(mode&4)!=0?null:text(a),right=(mode&8)!=0?null:text(b);
  try{return ((mode&2)!=0?left.regionMatches((mode&1)!=0,offset,right,otherOffset,length):left.regionMatches(offset,right,otherOffset,length))?1:0;}catch(NullPointerException error){return -1;}
 }
}
