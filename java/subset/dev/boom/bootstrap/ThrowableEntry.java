package dev.boom.bootstrap;

// Reaches the actual pinned JDK constructor/field/stack-trace paths.
// This remains an explicit failure probe until those runtime services exist.
public final class ThrowableEntry {
    public static int message(int kind) {
        Throwable value = kind == 0 ? new Throwable("base") : new IllegalStateException("derived");
        return value.getMessage().length();
    }
}
