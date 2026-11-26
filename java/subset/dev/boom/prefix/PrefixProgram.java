package dev.boom.prefix;
public final class PrefixProgram {
    static String pick(int n) {return switch(n&15) {
        case 0->"";case 1->"12345678";case 2->"1234567";case 3->"123456789";
        case 4->"1234567812345678";case 5->"1234567812345679";
        case 6->"a\0b";case 7->"\0";case 8->"\ud800X\udc00";
        case 9->"\ud800";case 10->"\udc00";case 11->"中é\u0100\uffff";
        case 12->"\ud83e\uddf1.\ud83e\uddf1";
        case 13->"12345678123456781234567812345678";
        case 14->"123456781234567812345678123456789";default->null;
    };}
    public static String objects(int n){String s=pick(n);if(s!=null)s.startsWith("",-1);return s;}
    public static int offset(int a,int b,int off){try{return pick(a).startsWith(pick(b),off)?1:0;}catch(NullPointerException e){return 73;}}
    public static int start(int a,int b){try{return pick(a).startsWith(pick(b))?1:0;}catch(NullPointerException e){return 73;}}
    public static int end(int a,int b){try{return pick(a).endsWith(pick(b))?1:0;}catch(NullPointerException e){return 73;}}
    public static int raw(int a,int b,int off){
        String s="["+(char)a+(char)b+"]",p=""+(char)a,q=""+(char)b;
        return (s.startsWith(p,off)?1:0)|(s.startsWith(q,1)?2:0)|(s.startsWith("[")?4:0)|(s.endsWith(q+"]")?8:0);
    }
    public static int dynamic(int n){String p="x"+n,s=p+"\ud800\0";return (s.startsWith(p)?1:0)|(s.endsWith("\ud800\0")?2:0)|(s.startsWith("",s.length())?4:0)|(s.startsWith(p,1)?8:0);}
    public static int nullOrder(int off){return offset(1,15,off)^offset(15,0,off)^start(15,15)^end(1,15);}
    public static int fullHeap(int n){String s=pick(n&7),p=pick((n>>>3)&7);int off=((n>>>6)&7)-2;return (s.startsWith(p,off)?1:0)|(s.startsWith(p)?2:0)|(s.endsWith(p)?4:0);}
    public static int parallel(int n){return fullHeap(n)^dynamic(n)^nullOrder(n-1024);}
}
