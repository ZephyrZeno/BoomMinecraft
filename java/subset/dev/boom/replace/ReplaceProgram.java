package dev.boom.replace;
public final class ReplaceProgram {
    static String pick(int n) {return switch(n&7) {
        case 0->"";case 1->"ababa";case 2->"a.b.a";case 3->"\0x\0";
        case 4->"\ud800A\udc00\ud800";case 5->"中é\u0100\uffff";
        case 6->"\ud83e\uddf1.\ud83e\uddf1";default->"\\/\\/";
    };}
    public static String objects(int n) {return pick(n).replace('z','z');}
    public static String pair(int oldChar,int newChar) {
        String s="["+(char)oldChar+(char)newChar+(char)oldChar+"]";
        return s.replace((char)oldChar,(char)newChar);
    }
    public static int relation(int n,int oldChar,int newChar) {
        String s=pick(n),r=s.replace((char)oldChar,(char)newChar);
        return r.hashCode()^r.length()*31^(s==r?0x13579:0x24680);
    }
    public static int twice(int n,int oldChar,int newChar) {
        String s=pick(n),a=s.replace((char)oldChar,(char)newChar),b=s.replace((char)oldChar,(char)newChar);
        return a.hashCode()^(a==b?17:23)^(a.equals(b)?29:31);
    }
    public static int dynamic(int n) {
        String s="x"+n+"\ud800x",r=s.replace('x',(char)n);
        return r.hashCode()^r.length()^(s==r?0x1234:0x5678);
    }
    public static int allocation(int n) {String s="ababa";return s.replace('a',(n&1)==0?'b':'a')==s?1:2;}
    public static int fullHeap(int n) {
        try {String s="ababa";String r=s.replace((n&3)==0?'x':'a',(n&3)==1?'a':'b');return r.length()+(s==r?16:32);}
        catch(OutOfMemoryError e){return 97;}
    }
    public static int nullReceiver(int n) {
        try {return ((String)null).replace((char)n,(char)n).length();}
        catch(NullPointerException e){return 73;}
    }
    public static int parallel(int n) {return relation(n,(n&1)==0?'a':'.',(char)(n>>>1));}
}
