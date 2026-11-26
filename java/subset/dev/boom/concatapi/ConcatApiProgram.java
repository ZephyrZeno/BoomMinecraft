package dev.boom.concatapi;

/** Guest bytecode fixtures; all guest String execution is translated to MASM. */
public final class ConcatApiProgram {
    static final String[] TEXT = {"", "A", "abc", "\u0000", "中", "Σ", "İı",
        "\ud800", "\udc00", "\ud801\udc00", "x\ud800y", "\udc00\ud800",
        "longer ASCII string", "a\u0000b", "🧱", "ßKſ"};
    static String unit(int n) { return String.valueOf((char)n); }
    public static int literals(int n) {
        String a = TEXT[n & 15], b = TEXT[(n >>> 4) & 15], c = a.concat(b);
        if (!c.equals(a + b)) return -1;
        if (b.isEmpty() ? c != a : c == a || c == b) return -2;
        return c.hashCode() * 31 + c.length();
    }
    public static int units(int a, int b) {
        String c = unit(a).concat(unit(b));
        return c.hashCode() ^ (c.charAt(0) << 16) ^ c.charAt(1);
    }
    public static int dynamic(int n) {
        String a = "prefix-" + n, b = "-\ud800-\u0000-🧱-" + (n ^ 17);
        String c = a.concat(b);
        return c.equals(a + b) ? c.hashCode() : -1;
    }
    public static int chain(int n) {
        String s = "";
        for (int i = 0; i < 31; i++) s = s.concat(TEXT[(n + i) & 15]);
        return s.hashCode() * 31 + s.length();
    }
    public static int copyIdentity(int n) {
        String a = "dynamic-" + n;
        int hash = a.hashCode();
        String b = "".concat(a);
        return b != a && b.equals(a) && b.hashCode() == hash && b.concat("") == b ? n + 71 : -1;
    }
    public static int interned(int n) {
        String a = TEXT[n & 15], b = "".concat(a);
        return b.intern() == a ? n + 73 : -1;
    }
    public static int nullSuffix(int n) {
        try { return TEXT[n & 15].concat(null).length(); }
        catch (NullPointerException e) { return n + 79; }
    }
    public static int nullReceiver(int n) {
        try { return ((String)null).concat(TEXT[n & 15]).length(); }
        catch (NullPointerException e) { return n + 83; }
    }
    public static int parallel(int n) { return dynamic(n) ^ literals(n); }
    public static int allocation(int n) {
        switch (n & 3) {
            case 0: return "abc".concat("").length();
            case 1: return "".concat("abc").length();
            case 2: return "abc".concat("A").length();
            default: return "abc".concat("abc").length();
        }
    }
    public static int fullHeap(int n) {
        try { return allocation(n); }
        catch (OutOfMemoryError e) { return 89; }
    }
    /** Returns guest references to the external verification harness. */
    public static String objects(int n) {
        switch (n & 7) {
            case 0: return "";
            case 1: return "abc";
            case 2: return "A";
            case 3: return "".concat("abc");
            case 4: return "abc".concat("A");
            case 5: return "abc".concat("");
            case 6: return "abc".concat("abc");
            default: return "\ud800\u0000".concat("\udc00🧱");
        }
    }
}
