package dev.boom.typechecks;
import java.io.Serializable;
public final class TypeEntry {
    static Object value(int kind, int seed) {
        switch(kind & 15) {
            case 0: return null;
            case 1: return "hello";
            case 2: return new Box(seed);
            case 3: return new Other(seed);
            case 4: return new int[3];
            case 5: return new long[2];
            case 6: return new byte[5];
            case 7: return new boolean[7];
            case 8: return new char[4];
            case 9: return new float[2];
            case 10: return new double[2];
            case 11: return new short[3];
            case 12: return new Box[2];
            case 13: return new String[2];
            case 14: return String.class;
            default: return new Class<?>[2];
        }
    }
    public static int checks(int kind, int seed) {
        Object v=value(kind,seed);
        return (v instanceof Object ? 1 : 0) | (v instanceof String ? 2 : 0)
            | (v instanceof Box ? 4 : 0) | (v instanceof Other ? 8 : 0)
            | (v instanceof CharSequence ? 16 : 0) | (v instanceof Serializable ? 32 : 0)
            | (v instanceof Cloneable ? 64 : 0) | (v instanceof Object[] ? 128 : 0)
            | (v instanceof int[] ? 256 : 0) | (v instanceof long[] ? 512 : 0)
            | (v instanceof String[] ? 1024 : 0) | (v instanceof Class<?> ? 2048 : 0)
            | (v instanceof Marker ? 4096 : 0);
    }
    public static int stringCast(int kind, int seed) { String v=(String)value(kind,seed); return v==null ? -1 : v.length(); }
    public static int boxCast(int kind, int seed) { Box v=(Box)value(kind,seed); return v==null ? -1 : v.read(); }
    public static int interfaceCast(int kind, int seed) { Serializable v=(Serializable)value(kind,seed); return v==null ? 0 : 1; }
    public static int primitiveArrayCast(int kind, int seed) { int[] v=(int[])value(kind,seed); return v==null ? -1 : v.length; }
    public static int stringArrayCast(int kind, int seed) { String[] v=(String[])value(kind,seed); return v==null ? -1 : v.length; }
    public static int covariantCast(int kind, int seed) { Object[] v=(Object[])value(kind,seed); return v==null ? 0 : ((String[])v).length; }
    public static int classCast(int kind, int seed) { Class<?> v=(Class<?>)value(kind,seed); return v==null ? 0 : v.getName().hashCode(); }
    public static int name(int kind, int seed) { return value(kind,seed).getClass().getName().hashCode(); }
    public static int mirrorIdentity(int kind, int seed) { return value(kind,seed).getClass()==value(kind,seed).getClass() ? 1 : 0; }
    public static int actualString(int ignored) { return "literal".getClass()==String.class ? 1 : 0; }
    public static int nullMetadataOnly(int ignored) { MetadataOnly value=(MetadataOnly)null; return value==null ? 1 : 0; }
    static Serializable serializable(boolean branch) { return branch ? "hello" : new int[1]; }
    public static int referenceJoin(int branch) { Serializable v=serializable(branch!=0); return v.getClass().isArray() ? 1 : 0; }
    static Object localJoin(boolean branch, int seed) { Object result; if(branch)result=new Box(seed);else result="hello";return result; }
    public static int localJoinCast(int branch, int seed) { return ((Box)localJoin(branch!=0,seed)).value; }
    public static int dynamicString(int seed) { Object value="I:"+seed; return ((String)value).hashCode() ^ value.getClass().getName().hashCode(); }
    public static int nullCast(int ignored) { return (String)null==null ? 1 : 0; }
}
