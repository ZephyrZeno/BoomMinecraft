package dev.boom.identity;
public final class HashExceptions {
    static final class Throwing {
        int calls;
        public int hashCode() { calls++; throw new IllegalStateException("hash failure"); }
    }
    public static int nullReceiver(int n) {
        try { return ((Object)null).hashCode(); }
        catch (NullPointerException e) { return n + 43; }
    }
    public static int throwing(int n) {
        Throwing a = new Throwing(); Object o = a;
        int identity = System.identityHashCode(o);
        if (a.calls != 0) return -1;
        try { o.hashCode(); return -2; }
        catch (IllegalStateException e) {
            return a.calls == 1 && System.identityHashCode(o) == identity ? n + 47 : -3;
        }
    }
    public static int nullArray(int n) {
        try { return ((int[])null).hashCode(); }
        catch (NullPointerException e) { return n + 49; }
    }
    public static int nullOpaque(int n) {
        try { return ((Class<?>)null).hashCode(); }
        catch (NullPointerException e) { return n + 51; }
    }
}
