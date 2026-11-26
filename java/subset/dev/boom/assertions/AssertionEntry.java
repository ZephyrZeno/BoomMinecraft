package dev.boom.assertions;

public final class AssertionEntry {
    public static Class<?> choose(int selector) {
        switch(selector) {
            case 0:return AssertionEntry.class;
            case 1:return Marker.class;
            case 2:return Token.class;
            case 3:return Dormant.class;
            case 4:return Throwable.class;
            case 5:return java.io.File.class;
            case 6:return java.util.List.class;
            case 7:return String.class;
            case 8:return int[].class;
            case 9:return AssertionEntry[].class;
            case 10:return int[].class.getComponentType();
            case 11:return boolean[].class.getComponentType();
            case 12:return byte[].class.getComponentType();
            case 13:return short[].class.getComponentType();
            case 14:return char[].class.getComponentType();
            case 15:return long[].class.getComponentType();
            case 16:return float[].class.getComponentType();
            case 17:return double[].class.getComponentType();
            case 18:return null;
            default:return Token.class;
        }
    }
    public static int query(int selector) { return choose(selector).desiredAssertionStatus()?1:0; }
    public static int actual(int selector) {
        Object value=selector==0?"bootstrap":new Token();
        return value.getClass().desiredAssertionStatus()?1:0;
    }
    public static int cached(int ignored) { return (Init.value?1:0)+Init.count*10; }
    public static int noInit(int ignored) { return (Dormant.class.desiredAssertionStatus()?1:0)+State.ran*100; }
}
interface Marker {}
final class Token {}
final class State { static int ran; }
final class Dormant { static { State.ran++; } }
final class Init {
    static final boolean value=Init.class.desiredAssertionStatus();
    static int count;
    static {count++;}
}
