package dev.boom.bootstrap;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.OptionalDouble;

// JDK bodies are never copied here: the compiler must read the pinned java.base image.
public final class BootstrapEntry {
    static OptionalInt held;
    public static int nullChecks(int selector) {
        Object value = selector == 0 ? null : new BootstrapToken();
        return (Objects.isNull(value) ? 1 : 2) + (Objects.nonNull(value) ? 4 : 8);
    }
    public static int optionalInt(int value, int fallback) {
        OptionalInt result = (value & 1) == 0 ? OptionalInt.empty() : OptionalInt.of(value);
        return result.orElse(fallback) ^ (result.isPresent() ? 0x5a : 0x3c) ^ (result.isEmpty() ? 0x1234 : 0x5678);
    }
    public static long optionalLong(long value, long fallback) {
        OptionalLong result = (value & 1) == 0 ? OptionalLong.empty() : OptionalLong.of(value);
        return result.orElse(fallback) ^ (result.isPresent() ? 0x5aL : 0x3cL) ^ (result.isEmpty() ? 0x1234L : 0x5678L);
    }
    public static double optionalDouble(double value, double fallback, int present) {
        OptionalDouble result = present == 0 ? OptionalDouble.empty() : OptionalDouble.of(value);
        return result.orElse(fallback);
    }
    public static int retained(int value) {
        if (held == null) held = OptionalInt.of(value);
        return held.orElse(123);
    }
}
final class BootstrapToken {}
