package dev.boom.storage;
public final class StorageProgram {
    public static String snapshot(StringBuilder value) { return value.toString(); }
    public static int capacity(StringBuilder value) { return value.capacity(); }
    public static int floatBits(int bits) { return Float.floatToRawIntBits(Float.intBitsToFloat(bits)); }
    public static long doubleBits(long bits) { return Double.doubleToRawLongBits(Double.longBitsToDouble(bits)); }
    public static int rawFloat(float value) { return Float.floatToRawIntBits(value); }
    public static long rawDouble(double value) { return Double.doubleToRawLongBits(value); }
    public static int canonicalFloat(int bits) { return Float.floatToIntBits(Float.intBitsToFloat(bits)); }
    public static long canonicalDouble(long bits) { return Double.doubleToLongBits(Double.longBitsToDouble(bits)); }
    public static int classNames(int n) {
        Class<?> type;
        String expected;
        switch(n&7){
            case 0: type=int.class;expected="int";break;
            case 1: type=void.class;expected="void";break;
            case 2: type=String.class;expected="class java.lang.String";break;
            case 3: type=StorageProgram.class;expected="class dev.boom.storage.StorageProgram";break;
            case 4: type=byte[].class;expected="class [B";break;
            case 5: type=String[][].class;expected="class [[Ljava.lang.String;";break;
            case 6: type=Runnable.class;expected="interface java.lang.Runnable";break;
            default:type=Object.class;expected="class java.lang.Object";
        }
        return type.toString().equals(expected)?n+73:-1;
    }
    public static int nullClass(int n) {
        try { return ((Class<?>)null).toString().length(); }
        catch(NullPointerException e) { return n+79; }
    }
    public static String originalBuilder(int n) { return new StringBuilder(n&31).append("x").toString(); }
}
