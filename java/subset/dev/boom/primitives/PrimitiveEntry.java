package dev.boom.primitives;

public final class PrimitiveEntry {
    static Class<?> select(int n) {
        return switch (n & 15) {
            case 0 -> Boolean.TYPE;
            case 1 -> Byte.TYPE;
            case 2 -> Character.TYPE;
            case 3 -> Short.TYPE;
            case 4 -> Integer.TYPE;
            case 5 -> Long.TYPE;
            case 6 -> Float.TYPE;
            case 7 -> Double.TYPE;
            case 8 -> Void.TYPE;
            default -> null;
        };
    }
    static Class<?> component(int n) {
        return switch (n & 15) {
            case 0 -> boolean[].class.getComponentType();
            case 1 -> byte[].class.getComponentType();
            case 2 -> char[].class.getComponentType();
            case 3 -> short[].class.getComponentType();
            case 4 -> int[].class.getComponentType();
            case 5 -> long[].class.getComponentType();
            case 6 -> float[].class.getComponentType();
            case 7 -> double[].class.getComponentType();
            case 8 -> Void.TYPE;
            default -> null;
        };
    }
    public static int name(int n) { return select(n).getName().hashCode(); }
    public static int identity(int n) { return select(n) == component(n) ? 1 : 0; }
    public static int traits(int n) {
        Class<?> c = select(n);
        return (c.isPrimitive() ? 1 : 0) | (c.isArray() ? 2 : 0) | (c.isInterface() ? 4 : 0)
            | (c.getSuperclass() == null ? 8 : 0) | (c.getComponentType() == null ? 16 : 0)
            | (c.getModule() == String.class.getModule() ? 32 : 0)
            | (c.getClass() == Class.class ? 64 : 0) | (c.desiredAssertionStatus() ? 128 : 0);
    }
    public static int assignable(int a, int b) { return select(a).isAssignableFrom(select(b)) ? 1 : 0; }
    public static int parallel(int n) { return identity(n % 9) + traits(n % 9) * 4; }
}
