package dev.boom.casing;

/** Guest fixtures: String calls are translated to the ASM runtime. */
public final class CaseProgram {
    static final String[] LEFT = {"A","AbC","","Σ","Σ","ß","ß","İ","ı","µ","\ud801\udc00","\ud800X","\udc00X","\ud800\udc00","K","ſ"};
    static final String[] RIGHT = {"a","aBc","","σ","ς","SS","ẞ","i","I","μ","\ud801\udc28","\ud800x","\udc00x","\ud800\udc01","k","S"};
    static String scalar(int n) {
        if ((n >>> 16) == 0) return String.valueOf((char)n);
        int x = n - 0x10000;
        return String.valueOf((char)((x >>> 10) + 0xd800)) + (char)((x & 1023) + 0xdc00);
    }
    public static int compare(int a, int b) { return scalar(a).equalsIgnoreCase(scalar(b)) ? 1 : 0; }
    public static int literals(int n) { int i = n & 15; return LEFT[i].equalsIgnoreCase(RIGHT[i]) ? n + 17 : n + 31; }
    public static int longValues(int n) {
        String a = "prefix-Σ-\ud801\udc00-" + n + "-\ud800-tail";
        String b = "PREFIX-ς-\ud801\udc28-" + n + "-\ud800-TAIL";
        return a.equalsIgnoreCase(b) ? n + 41 : 0;
    }
    public static int unequal(int n) { return ("same-" + n).equalsIgnoreCase("same-" + (n ^ 1)) ? 0 : n + 47; }
    public static int nullArgument(int n) { return "x".equalsIgnoreCase(null) ? 0 : n + 53; }
    public static int nullReceiver(int n) {
        try { return ((String)null).equalsIgnoreCase("x") ? 1 : 2; }
        catch (NullPointerException e) { return n + 59; }
    }
    public static int parallel(int n) { return literals(n); }
    public static int identity(int n) { String a = "value-" + n; return a.equalsIgnoreCase(a) ? n + 61 : 0; }
    public static int indexOf(int cp) { return "A\u0000Σ\ud801\udc00x\ud800y\udc00A".indexOf(cp); }
    public static int indexFrom(int cp, int start) { return "A\u0000Σ\ud801\udc00x\ud800y\udc00A".indexOf(cp,start); }
    public static int suffix(int begin) { return "A\u0000Σ\ud801\udc00x\ud800y\udc00A".substring(begin).hashCode(); }
    public static int range(int begin, int end) { return "A\u0000Σ\ud801\udc00x\ud800y\udc00A".substring(begin,end).hashCode(); }
    public static int emptyIdentity(int n) { return "value".substring(n & 3,n & 3) == "" ? n + 67 : 0; }
    public static int fullIdentity(int n) { String a = "prefix-" + n; return a.substring(0) == a && a.substring(0,a.length()) == a ? n + 71 : 0; }
    public static int substringOom(int n) {
        try { return "constant-text".substring(1).length() + n; }
        catch (OutOfMemoryError e) { return 89; }
    }
}
