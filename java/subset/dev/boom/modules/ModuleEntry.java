package dev.boom.modules;

public final class ModuleEntry {
    static Class<?> select(int which) {
        return switch (which & 15) {
            case 0 -> ModuleEntry.class;
            case 1 -> Token.class;
            case 2 -> Dormant.class;
            case 3 -> Marker.class;
            case 4 -> String.class;
            case 5 -> Runtime.class;
            case 6 -> Module.class;
            case 7 -> Throwable.class;
            case 8 -> int[].class;
            case 9 -> Token[].class;
            case 10 -> String[][].class;
            case 11 -> int[][].class;
            case 12 -> int[].class.getComponentType();
            case 13 -> boolean[].class.getComponentType();
            case 14 -> java.util.List.class;
            default -> java.io.File.class;
        };
    }
    public static int named(int which) { return select(which).getModule().isNamed() ? 1 : 0; }
    public static int name(int which) { String name = select(which).getModule().getName(); return name == null ? -1 : name.hashCode(); }
    public static int identity(int a, int b) { return select(a).getModule() == select(b).getModule() ? 1 : 0; }
    public static int literalIdentity(int which) { return select(which).getModule().getName() == "java.base" ? 1 : 0; }
    public static int actual(int which) { Object value = which == 0 ? "hello" : new Token(); return value.getClass().getModule().isNamed() ? 1 : 0; }
    public static int type(int which) {
        Object value = select(which).getModule();
        return (value instanceof Module ? 1 : 0) | (((Module)value).isNamed() ? 2 : 0)
            | (value.getClass() == Module.class ? 4 : 0)
            | (value.getClass().getModule() == String.class.getModule() ? 8 : 0);
    }
    public static int cached(int ignored) { return Init.value + Init.count * 10; }
    public static int noInit(int ignored) { return (Dormant.class.getModule().isNamed() ? 1 : 0) + State.ran * 100; }
    public static int nullClass(int ignored) { Class<?> value = null; return value.getModule().isNamed() ? 1 : 0; }
    public static int nullName(int ignored) { Module value = null; return value.getName().length(); }
    public static int nullNamed(int ignored) { Module value = null; return value.isNamed() ? 1 : 0; }
    public static int combined(int which) {
        long before = System.nanoTime();
        return (select(which).getModule().isNamed() ? 1 : 0)
            | (select(which).desiredAssertionStatus() ? 2 : 0)
            | (System.nanoTime() - before >= 0 ? 4 : 0);
    }
    public static int unsupportedLayer(int ignored) { return String.class.getModule().getLayer() == null ? 0 : 1; }
    public static int unsupportedDescriptor(int ignored) { return String.class.getModule().getDescriptor() == null ? 0 : 1; }
    public static int unsupportedPackages(int ignored) { return String.class.getModule().getPackages().size(); }
}
interface Marker {}
final class Token {}
final class State { static int ran; }
final class Dormant { static { State.ran++; } }
final class Init {
    static int count;
    static int value;
    static { count++; value = (ModuleEntry.class.getModule().isNamed() ? 2 : 0) + (String.class.getModule().isNamed() ? 1 : 0); }
}
