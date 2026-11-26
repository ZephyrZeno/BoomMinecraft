package dev.boom.monitors;
import java.io.ByteArrayInputStream;
import java.io.InputStream;

public final class MonitorEntry {
    private static int total;
    private static synchronized int step(int n) { total += n; return total; }
    private static synchronized int recurse(int n) { return n == 0 ? 7 : recurse(n - 1) + 1; }
    public static int staticEntry(int n) { total = 0; return step(n); }
    public static int recursiveStatic(int n) { return recurse(n & 15); }
    public static int recursiveInstance(int n) { return new Counter().recurse(n & 15); }
    public static int instance(int n) { Counter c = new Counter(); return c.add(n) + c.add(3); }
    public static int throwing(int n) { return new Counter().divide(n); }
    public static int nullReceiver(int n) { Counter c = null; return c.add(n); }
    public static long wide(long a, long b) { return new Counter().wide(a, b); }
    public static double floating(double a, double b) { return new Counter().floating(a, b); }
    public static int nested(int n) { return new Counter().nested(n); }
    public static int voidResult(int n) { Counter c = new Counter(); c.set(n); return c.add(0); }
    public static int abstractDispatch(int n) { AbstractReader r = new RealReader(); return r.value(n); }
    public static int inputStream(int n) throws Exception {
        byte[] data = new byte[(n & 63) + 3];
        for (int i = 0; i < data.length; i++) data[i] = (byte)(i * 17 + n);
        InputStream s = new ByteArrayInputStream(data);
        int first = s.read();
        s.mark(99); long skipped = s.skip((n & 7) - 2);
        int remaining = s.available(); s.reset();
        int sum = first;
        for (int b; (b = s.read()) != -1;) sum += b;
        s.close();
        return sum + remaining * 1009 + (int)skipped * 100003;
    }
    public static synchronized int parallelStatic(int unused) { return ++total; }
    public static int parallelInstance(int unused) { return Shared.counter.add(1); }
    public static int unsupportedWait(int unused) throws Exception { new Counter().wait(); return 1; }
    public static int unsupportedBlock(int n) { Counter c = new Counter(); synchronized(c) { return c.add(n); } }
}
final class Counter {
    private int value;
    synchronized int add(int n) { value += n; return value; }
    synchronized int recurse(int n) { return n == 0 ? 3 : recurse(n - 1) * 2; }
    synchronized int divide(int n) { return 123 / n; }
    synchronized long wide(long a, long b) { return a ^ b; }
    synchronized double floating(double a, double b) { return a + b; }
    synchronized int nested(int n) { return add(n) + add(7); }
    synchronized void set(int n) { value = n; }
}
final class Shared { static final Counter counter = new Counter(); }
abstract class AbstractReader { int value(int n) { return System.identityHashCode(this); } }
final class RealReader extends AbstractReader { synchronized int value(int n) { return n * 13 + 1; } }
