package dev.boom.layers;
import java.util.Optional;

public final class LayerEntry {
    static ModuleLayer layer(int empty) { return empty == 0 ? ModuleLayer.boot() : ModuleLayer.empty(); }
    public static int bootIdentity(int ignored) {
        ModuleLayer b = ModuleLayer.boot(), e = ModuleLayer.empty();
        return (b != null ? 1 : 0) | (b == Runtime.class.getModule().getLayer() ? 2 : 0)
            | (b != e ? 4 : 0) | (e == ModuleLayer.empty() ? 8 : 0)
            | (b.getClass() == ModuleLayer.class ? 16 : 0);
    }
    public static int ofClass(int which) {
        Class<?> c = switch (which & 7) {
            case 0 -> LayerEntry.class;
            case 1 -> Dormant.class;
            case 2 -> Marker.class;
            case 3 -> String.class;
            case 4 -> int[].class;
            case 5 -> LayerEntry[].class;
            case 6 -> int[].class.getComponentType();
            default -> ModuleLayer.class;
        };
        ModuleLayer l = c.getModule().getLayer();
        return l == null ? 1 : l == ModuleLayer.boot() ? 3 : -1;
    }
    public static int present(int name, int empty) { return layer(empty).findModule(Names.at(name)).isPresent() ? 1 : 0; }
    public static int name(int name, int empty) { Module m = layer(empty).findModule(Names.at(name)).orElse(null); return m == null ? -1 : m.getName().hashCode(); }
    public static int identity(int name, int empty) {
        Module a = layer(empty).findModule(Names.at(name)).orElse(null);
        Module b = layer(empty).findModule(Names.at(name)).orElse(null);
        return (a == b ? 1 : 0) | (a == null ? 2 : 0)
            | (a != null && a.getLayer() == ModuleLayer.boot() ? 4 : 0)
            | (a != null && a.getClass() == Module.class ? 8 : 0);
    }
    public static int dynamic(int name, int suffix) { return ModuleLayer.boot().findModule(Names.at(name) + ((suffix & 1) == 0 ? "" : "\0")).isPresent() ? 1 : 0; }
    public static int roundTrip(int name) { Module m = ModuleLayer.boot().findModule(Names.at(name)).orElse(null); return m != null && m.getLayer() == ModuleLayer.boot() ? 1 : 0; }
    public static int direct(int n) { return layer(n & 1) == ModuleLayer.boot() ? 1 : 0; }
    public static int types(int which) { Object l = layer(which); return (l instanceof ModuleLayer ? 1 : 0) | ((ModuleLayer)l == ModuleLayer.boot() ? 2 : 0) | (l.getClass().getModule() == String.class.getModule() ? 4 : 0); }
    public static int noInit(int ignored) { return (Dormant.class.getModule().getLayer() == null ? 1 : 0) + State.ran * 100; }
    public static int nullModule(int ignored) { Module m = null; return m.getLayer() == null ? 1 : 0; }
    public static int nullLayer(int ignored) { ModuleLayer l = null; return l.findModule("java.base").isPresent() ? 1 : 0; }
    public static int cached(int ignored) { return Init.value + Init.count * 10; }
    public static int combined(int name) {
        long before = System.nanoTime();
        return (ModuleLayer.boot().findModule(Names.at(name)).isPresent() ? 1 : 0)
            | (LayerEntry.class.desiredAssertionStatus() ? 2 : 0) | (System.nanoTime() - before >= 0 ? 4 : 0);
    }
    public static int unsupported(int ignored) { return ModuleLayer.boot().modules().size(); }
}
interface Marker {}
final class State { static int ran; }
final class Dormant { static { State.ran++; } }
final class Init {
    static int count;
    static int value;
    static { count++; value = (ModuleLayer.boot() == Runtime.class.getModule().getLayer() ? 1 : 0)
        | (ModuleLayer.boot() != ModuleLayer.empty() ? 2 : 0)
        | (ModuleLayer.boot().findModule("java.base").orElse(null) == Runtime.class.getModule() ? 4 : 0); }
}
