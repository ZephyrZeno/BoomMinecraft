package dev.boom.identity;

/** Identity relations are portable; JVM-specific hash values are not an oracle. */
public final class HashProgram {
    interface Hasher { int hashCode(); }
    static class Base { final int value; Base(int n) { value = n; } }
    static final class Plain extends Base implements Hasher { Plain(int n) { super(n); } }
    static final class Override extends Base implements Hasher {
        int calls;
        Override(int n) { super(n); }
        public int hashCode() { calls++; return value ^ 0x13579bdf; }
    }
    static final class Super extends Base {
        Super(int n) { super(n); }
        public int hashCode() { return super.hashCode() ^ value; }
        int raw() { return super.hashCode(); }
    }
    static final class Sync extends Base {
        int calls;
        Sync(int n) { super(n); }
        public synchronized int hashCode() { calls++; return value ^ 0x2468ace0; }
    }
    static final Plain SHARED = new Plain(17);
    static final Sync SYNCHRONIZED = new Sync(23);
    public static int plain(int n) {
        Object a = new Plain(n);
        int h = a.hashCode();
        return h == System.identityHashCode(a) && a.hashCode() == h ? n + 7 : -1;
    }
    public static int overridden(int n) {
        Override a = new Override(n); Object o = a;
        int h = System.identityHashCode(o);
        if (a.calls != 0 || o.hashCode() != (n ^ 0x13579bdf) || a.calls != 1) return -1;
        return System.identityHashCode(o) == h && a.calls == 1 ? n + 11 : -2;
    }
    public static int superHash(int n) {
        Super a = new Super(n); Object o = a;
        int h = System.identityHashCode(a);
        return a.raw() == h && o.hashCode() == (h ^ n) ? n + 13 : -1;
    }
    public static int interfaceHash(int n) {
        Hasher a = (n & 1) == 0 ? new Plain(n) : new Override(n);
        int expected = (n & 1) == 0 ? System.identityHashCode(a) : n ^ 0x13579bdf;
        return a.hashCode() == expected ? n + 17 : -1;
    }
    public static int stringHash(int n) {
        String a = "content-\u0000-🧱"; Object o = a;
        int h = System.identityHashCode(o);
        return o.hashCode() == a.hashCode() && System.identityHashCode(a) == h ? n + 19 : -1;
    }
    static Object array(int n) {
        int len = (n & 7) + 1;
        switch ((n >>> 3) & 7) {
            case 0: return new int[len];
            case 1: return new byte[len];
            case 2: return new char[len];
            case 3: return new long[len];
            case 4: return new double[len];
            case 5: return new String[len];
            case 6: return new Class<?>[len];
            default: return new Object[len];
        }
    }
    public static int arrays(int n) {
        Object a = array(n); int h = System.identityHashCode(a);
        return a.hashCode() == h && a.hashCode() == h ? n + 23 : -1;
    }
    public static int directArray(int n) {
        int[] a=new int[(n&7)+1];
        String[] b=new String[(n&3)+1];
        return a.hashCode()==System.identityHashCode(a)&&b.hashCode()==System.identityHashCode(b)?n+27:-1;
    }
    public static int opaque(int n) {
        Object a;
        switch (n & 3) {
            case 0: a = HashProgram.class; break;
            case 1: a = int.class; break;
            case 2: a = HashProgram.class.getModule(); break;
            default: a = ModuleLayer.boot();
        }
        return a.hashCode() == System.identityHashCode(a) ? n + 29 : -1;
    }
    public static int nullIdentity(int n) { return System.identityHashCode(null) == 0 ? n + 31 : -1; }
    public static int directOpaque(int n) {
        Class<?> a=HashProgram.class;
        Module b=a.getModule();
        ModuleLayer c=ModuleLayer.boot();
        return a.hashCode()==System.identityHashCode(a)&&b.hashCode()==System.identityHashCode(b)
            && c.hashCode()==System.identityHashCode(c)?n+33:-1;
    }
    public static int hot(int n) {
        return SHARED.hashCode() == System.identityHashCode(SHARED) ? n + 37 : -1;
    }
    public static int parallel(int n) {
        int identity = System.identityHashCode(SYNCHRONIZED);
        int h = SYNCHRONIZED.hashCode();
        return identity == System.identityHashCode(SYNCHRONIZED) && h == (23 ^ 0x2468ace0)
            && SHARED.hashCode() == System.identityHashCode(SHARED) ? n + 41 : -1;
    }
    public static Object objects(int n) {
        Object a;
        switch (n & 7) {
            case 0: a = SHARED; break;
            case 1: a = new Plain(n); break;
            case 2: a = array(n); break;
            case 3: a = "content"; break;
            case 4: a = HashProgram.class; break;
            case 5: a = int.class; break;
            case 6: a = HashProgram.class.getModule(); break;
            default: a = ModuleLayer.boot();
        }
        System.identityHashCode(a);
        return a;
    }
}
