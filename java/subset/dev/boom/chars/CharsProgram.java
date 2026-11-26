package dev.boom.chars;
public final class CharsProgram {
    static String pick(int n) { return switch(n & 7) {
        case 0 -> ""; case 1 -> "ababa"; case 2 -> "\0x\0";
        case 3 -> "\ud800A\udc00\udfff"; case 4 -> "中é\u0100\uffff";
        case 5 -> "\ud83e\uddf1.\ud83e\uddf1"; case 6 -> "\\/\\/"; default -> "ASCII";
    }; }
    public static String objects(int n) {
        String s=pick(n); char[] a=s.toCharArray();
        if(a.length!=0) a[0]^=1;
        return s;
    }
    public static char[] array(int n) { return pick(n).toCharArray(); }
    public static char[] pair(int a,int b) { return ("["+(char)a+(char)b+"\0\ud800\udfff]").toCharArray(); }
    static int fold(char[] a) { int h=0; for(int i=0;i<a.length;i++) h=h*31+a[i]; return h; }
    public static int relation(int n,int value) {
        String s=pick(n);char[] a=s.toCharArray(),b=s.toCharArray();
        int h=fold(a); if(a.length!=0) a[0]=(char)value;
        return h^fold(b)^fold(a)^s.hashCode()^(a==b?17:23)^a.length*13;
    }
    public static int twice(int n) {
        String s=pick(n);char[] a=s.toCharArray(),b=s.toCharArray();
        return fold(a)^s.hashCode()^(a!=b?37:41)^a.length;
    }
    public static int dynamic(int n) {
        String s="x"+n+"\ud800\0"; char[] a=s.toCharArray();
        int h=fold(a);a[0]=(char)n;return h^s.hashCode()^fold(a);
    }
    public static int bounds(int n) {
        char[] a=pick(n).toCharArray();
        try { return a[(n&8)==0?-1:a.length]; }
        catch(ArrayIndexOutOfBoundsException e) { return 71+a.length; }
    }
    public static int nullReceiver(int n) {
        try { return ((String)null).toCharArray().length+n; }
        catch(NullPointerException e) { return 73; }
    }
    public static int fullHeap(int n) {
        try { return pick(n&1).toCharArray().length+19; }
        catch(OutOfMemoryError e) { return 97; }
    }
    public static int copyTypes(int n) {
        char[] a=pick(n).toCharArray(),b=a.clone();
        System.arraycopy(a,0,b,0,a.length);
        return fold(b)^a.length^(a.getClass()==char[].class?13:17)^(a!=b?23:29);
    }
    public static int parallel(int n) { return relation(n,n>>>1)^dynamic(n); }
}
