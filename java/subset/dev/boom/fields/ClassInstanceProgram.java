package dev.boom.fields;
public final class ClassInstanceProgram {
    interface Marker {}
    static class Root {}
    static final class Child extends Root implements Marker {}
    static final class Plain {}
    static int initialized;
    static final class Cold { static { initialized++; } }
    static Class<?> target(int kind) {
        return switch (kind) {
            case 0 -> Object.class; case 1 -> String.class; case 2 -> CharSequence.class;
            case 3 -> Root.class; case 4 -> Child.class; case 5 -> Marker.class;
            case 6 -> int[].class; case 7 -> Object[].class; case 8 -> String[].class;
            case 9 -> int[][].class; case 10 -> int.class; case 11 -> void.class;
            case 12 -> Cold.class; default -> null;
        };
    }
    static Object value(int kind) {
        return switch (kind) {
            case 0 -> null; case 1 -> "assembly"; case 2 -> new Root();
            case 3 -> new Child(); case 4 -> new Plain(); case 5 -> new int[2];
            case 6 -> new String[2]; case 7 -> new int[2][];
            case 8 -> new Object[2]; default -> new boolean[2];
        };
    }
    public static String run(int mode) {
        if (mode == 140) return initialized == 0 ? "uninitialized" : "initialized";
        try { return target(mode / 10).isInstance(value(mode % 10)) ? "true" : "false"; }
        catch (NullPointerException expected) { return "null-class"; }
    }
}
