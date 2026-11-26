package dev.boom.properties;

class ConstructorBase {
    public int base;
    ConstructorBase(int n) { base = n + 3; }
}
abstract class AbstractConstructor {
    protected AbstractConstructor() {}
}
public final class ConstructorProgram extends ConstructorBase {
    public static int initializationCount = initialize();
    public static ConstructorProgram escaped;
    public ConstructorProgram self;
    public int value;
    public long wide;
    public double decimal;
    private static int initialize() { initializationCount++; return initializationCount; }
    public ConstructorProgram() { this(17, 0x123456789abcdef0L, 2.5); }
    public ConstructorProgram(int n, long bits, double number) {
        super(n);
        value = n; wide = bits; decimal = number;
        self = this; escaped = this;
        if (n < 0) throw new IllegalArgumentException("constructor rejected value");
    }
}
