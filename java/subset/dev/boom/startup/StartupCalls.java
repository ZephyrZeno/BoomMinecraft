package dev.boom.startup;
public final class StartupCalls {
    public static int wide(int a0,int a1,int a2,int a3,int a4,int a5,int a6,int a7,int a8,int a9,
                           int a10,int a11,int a12,int a13,int a14,int a15,int a16,int a17,int a18,int a19) {
        return a0+3*a1+5*a2+7*a3+11*a4+13*a5+17*a6+19*a7+23*a8+29*a9+
               31*a10+37*a11+41*a12+43*a13+47*a14+53*a15+59*a16+61*a17+67*a18+71*a19;
    }
    public static int call(int x) {
        int keep = x ^ 0x61ab3c87;
        return wide(x,x+1,x+2,x+3,x+4,x+5,x+6,x+7,x+8,x+9,
                    x+10,x+11,x+12,x+13,x+14,x+15,x+16,x+17,x+18,x+19) ^ keep;
    }
    private static String text(int n) {
        return switch(n) {case 0->"";case 1->"aab\u0000a\uffff";case 2->"\ud83d\ude00x\ud83d\ude00";
                         case 3->"\ud800x\udc00\ud800";case 4->null;default->"localhost:25565:host";};
    }
    public static int last(int n,int cp) { return text(n).lastIndexOf(cp); }
    public static int lastFrom(int n,int cp,int from) { return text(n).lastIndexOf(cp,from); }
    public static int forward(int n,int cp,int from) { return text(n).indexOf(cp,from); }
    public static int slice(int a,int b) { return "012345".substring(a,b).hashCode(); }
    public static int strIndex(int n,int needle,int from) { return text(n).indexOf(text(needle),from); }
    public static int strLast(int n,int needle,int from) { return text(n).lastIndexOf(text(needle),from); }
    public static int strDefaults(int n,int needle) { return text(n).indexOf(text(needle))*31+text(n).lastIndexOf(text(needle)); }
    private static int calls;
    private static final class Sequence implements CharSequence {
        private final int kind;
        Sequence(int n) { kind=n; }
        public int length() { return text(kind).length(); }
        public char charAt(int n) { return text(kind).charAt(n); }
        public CharSequence subSequence(int a,int b) { return text(kind).substring(a,b); }
        public String toString() { calls++; return text(kind); }
    }
    public static int contains(int n,int needle) { calls=0;return (text(n).contains(new Sequence(needle))?1:0)+calls*4; }
    public static int containsOrder(int n,int needle) {
        calls=0;
        try { return (text(n).contains(new Sequence(needle))?1:0)+calls*4; }
        catch(NullPointerException e) { return calls*4+2; }
    }
    public static int test(int method,int a,int b,int c) {
        return switch(method) {
            case 0 -> call(a); case 1 -> last(a,b); case 2 -> lastFrom(a,b,c);
            case 3 -> forward(a,b,c); case 4 -> slice(a,b); case 5 -> strIndex(a,b,c);
            case 6 -> strLast(a,b,c); case 7 -> strDefaults(a,b); case 8 -> contains(a,b);
            default -> containsOrder(a,b);
        };
    }
}
