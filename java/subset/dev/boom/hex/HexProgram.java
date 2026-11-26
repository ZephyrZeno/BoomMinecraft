package dev.boom.hex;
public final class HexProgram {
    public static String intValue(int n) { return Integer.toHexString(n); }
    public static String longValue(long n) { return Long.toHexString(n); }
    public static int intRelations(int n) {
        String a=Integer.toHexString(n),b=Integer.toHexString(n);
        if(a==b||!a.equals(b)||a.length()<1||a.length()>8) return -1;
        if(a.length()>1&&a.charAt(0)=='0') return -2;
        return a.hashCode()^a.length();
    }
    public static int longRelations(long n) {
        String a=Long.toHexString(n),b=Long.toHexString(n);
        if(a==b||!a.equals(b)||a.length()<1||a.length()>16) return -1;
        if(a.length()>1&&a.charAt(0)=='0') return -2;
        return a.hashCode()^a.length();
    }
    public static int parallel(int n) {
        String a=Integer.toHexString(n*0x13579bdf);
        String b=Long.toHexString((((long)n)<<32)^(n*0x2468ace1L));
        return a.hashCode()^b.hashCode();
    }
    public static int allocation(int n) { return Integer.toHexString(n).length(); }
    public static int fullHeap(int n) {
        try { return Integer.toHexString(n).length(); }
        catch (OutOfMemoryError e) { return 89; }
    }
    public static int fullHeapLong(long n) {
        try { return Long.toHexString(n).length(); }
        catch (OutOfMemoryError e) { return 89; }
    }
}
