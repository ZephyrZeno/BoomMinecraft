package dev.boom.access.parent;
public class ProtectedBase {
    private int value;
    private long wide;
    protected ProtectedBase(int value) { this.value = value; }
    protected ProtectedBase(int value, long wide) { this(value); this.wide = wide; }
    public final int value() { return value; }
    public final long wide() { return wide; }
}
