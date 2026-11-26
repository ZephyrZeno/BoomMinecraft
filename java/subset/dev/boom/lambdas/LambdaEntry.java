package dev.boom.lambdas;

import java.util.function.*;

/** Original Java input for differential tests. Generated lambda templates never run on the JVM. */
public final class LambdaEntry {
    private final int value;
    private LambdaEntry(int value) { this.value = value; }
    private static int twice(int n) { return n * 2 + 3; }
    private int add(int n) { return value + n; }
    private static long wide(long n) { return n * 3; }
    private static String text(String s) { return s; }

    public static int stateless(int n) { IntUnaryOperator f = LambdaEntry::twice; return f.applyAsInt(n); }
    public static int capture(int a, int n) { IntUnaryOperator f = x -> a * 7 + x; return f.applyAsInt(n); }
    public static int bound(int a, int n) { IntUnaryOperator f = new LambdaEntry(a)::add; return f.applyAsInt(n); }
    public static int unbound(int a, int n) { Receiver f = LambdaEntry::add; return f.apply(new LambdaEntry(a), n); }
    public static int constructor(int a) { IntFunction<LambdaEntry> f = LambdaEntry::new; return f.apply(a).value; }
    public static int virtual(int which, int n) { Parent p = (which & 1) == 0 ? new Parent() : new Child(); IntUnaryOperator f = p::run; return f.applyAsInt(n); }
    public static int interfaceRef(int which, int n) { Task t = (which & 1) == 0 ? new Parent() : new Child(); TaskReceiver f = Task::run; return f.apply(t, n); }
    public static int defaultRef(int n) { DefaultTask t = new DefaultImpl(); IntUnaryOperator f = t::run; return f.applyAsInt(n); }
    public static long widen(int n) { IntToLongFunction f = LambdaEntry::wide; return f.applyAsLong(n); }
    public static double widenResult(int n) { IntToDoubleFunction f = LambdaEntry::twice; return f.applyAsDouble(n); }
    public static long wideCapture(long a, long b) { LongUnaryOperator f = x -> a ^ x; return f.applyAsLong(b); }
    public static double doubleCapture(double a, double b) { DoubleUnaryOperator f = x -> a + x; return f.applyAsDouble(b); }
    public static int mixed(int a, long b, float c, double d, int n) { IntUnaryOperator f = x -> a + (int)b + (int)c + (int)d + x; return f.applyAsInt(n); }
    public static int references(int n) { String s = (n & 1) == 0 ? "captured" : "\ud800\0z"; IntUnaryOperator f = x -> s.hashCode() + x; return f.applyAsInt(n); }
    public static int genericCast(int n) { Function<String, String> f = LambdaEntry::text; Object s = (n & 1) == 0 ? "lambda" : ""; return f.apply((String)s).hashCode(); }
    @SuppressWarnings({"rawtypes", "unchecked"})
    public static int badCast(int n) { Function f = (Function<String, String>)LambdaEntry::text; return ((String)f.apply(new LambdaEntry(n))).length(); }
    public static int discard(int n) { IntConsumer f = LambdaEntry::twice; f.accept(n); return n; }
    public static int nullBound(int n) { LambdaEntry p = null; IntUnaryOperator f = p::add; return f.applyAsInt(n); }
    public static int nullUnbound(int n) { Receiver f = LambdaEntry::add; return f.apply(null, n); }
    public static int nullableCapture(int n) { LambdaEntry p = null; IntUnaryOperator f = x -> p == null ? x : p.value; return f.applyAsInt(n); }
    public static int narrow(int aa, int bb, int cc, int dd, int n) { byte a = (byte)aa; short b = (short)bb; char c = (char)cc; boolean d = dd != 0; IntUnaryOperator f = x -> a + b + c + (d ? 11 : -11) + x; return f.applyAsInt(n); }
    public static int cached(int n) { return Cached.f.applyAsInt(n) + Cached.count * 100; }
    public static int special(int n) { return new Child().superReference(n); }
    public static int staticInterface(int n) { IntUnaryOperator f = StaticTask::run; return f.applyAsInt(n) + StaticTask.direct(n); }
    public static int alternate(int n) { IntUnaryOperator f = (IntUnaryOperator & java.io.Serializable)(x -> x + n); return f.applyAsInt(n); }
}
interface Receiver { int apply(LambdaEntry p, int n); }
interface TaskReceiver { int apply(Task p, int n); }
interface Task { int run(int n); }
interface StaticTask {
    private static int helper(int n) { return n * 11 + 3; }
    static int run(int n) { return helper(n); }
    static int direct(int n) { return helper(n) - 7; }
}
class Parent implements Task { public int run(int n) { return n + 5; } }
final class Child extends Parent {
    public int run(int n) { return n + 9; }
    int superReference(int n) { IntUnaryOperator f = super::run; return f.applyAsInt(n); }
}
interface DefaultTask { default int run(int n) { return n * 5 - 1; } }
final class DefaultImpl implements DefaultTask {}
final class Cached {
    static int count;
    static final IntUnaryOperator f;
    static { count++; String s = "root"; f = n -> s.hashCode() ^ n; }
}
