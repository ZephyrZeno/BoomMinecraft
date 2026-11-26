package dev.boom.access.child;
import dev.boom.access.parent.ProtectedBase;
import dev.boom.access.grandchild.Grandchild;

public class ConstructorProgram extends ProtectedBase {
    public ConstructorProgram(int value) { super(value * 7 + 1, ((long) value << 32) | 0xabcdef01L); }
    protected ConstructorProgram(int value, int unused) { this(value); }
    public static int child(int value) { return new ConstructorProgram(value).value(); }
    public static long wide(int value) { ConstructorProgram a = new ConstructorProgram(value); return a.wide() + a.value() * 31L; }
    public static int anonymous(int value) { return new ProtectedBase(value) { }.value(); }
    public static int chained(int value) { return new Grandchild(value).value(); }
    public static int enumValues(int value) {
        Value[] a = Value.values(), b = Value.values();
        int result = a != b && a.getClass() == b.getClass() ? 1 : 0;
        a[0] = null;
        if (b[0] == Value.ALPHA && b.length == 3) result += 2;
        return result + 31 * b[(value & 0x7fffffff) % 3].ordinal();
    }
    enum Value { ALPHA, BETA, GAMMA }
}
