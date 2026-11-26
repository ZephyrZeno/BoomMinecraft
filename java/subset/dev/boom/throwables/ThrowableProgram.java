package dev.boom.throwables;
import java.util.function.Supplier;

/** Original Throwable constructors and ordinary Java calls; not a game launch. */
public final class ThrowableProgram {
    public static Throwable last;
    private static Throwable held;
    private static final class Shadow extends RuntimeException {
        private Object backtrace;
        private int depth;
        private StackTraceElement[] stackTrace;
        private int fills;
        Shadow(String message, int n) {
            super(message);
            backtrace = this;
            depth = n;
            stackTrace = null;
        }
        @Override public synchronized Throwable fillInStackTrace() {
            fills++;
            return super.fillInStackTrace();
        }
        int ownDepth() {
            return depth + (backtrace == this ? 0 : 1000) + (stackTrace == null ? 0 : 2000);
        }
    }
    private static Throwable make(int n) {
        if ((n & 3) == 0) return new Throwable("base");
        if ((n & 3) == 1) return new IllegalStateException("derived");
        return new Shadow("shadow", n);
    }
    private static int answer(Throwable value, int n) {
        return n + value.getMessage().length() + (value.getCause() == null ? 32 : 0);
    }
    public static int message(int n) {
        last = make(n);
        return answer(last, n);
    }
    private static int inner(int n) {
        last = make(n);
        return answer(last, n);
    }
    public static int nested(int n) { return inner(n); }
    private static Throwable refillHere(Throwable value) { return value.fillInStackTrace(); }
    public static int refill(int n) {
        Throwable value = make(n);
        if (refillHere(value) != value) return 0;
        last = value;
        return answer(value, n);
    }
    public static int shadowRefill(int n) {
        Shadow value = new Shadow("shadow", n);
        refillHere(value);
        last = value;
        return value.ownDepth() + value.fills + value.getMessage().length();
    }
    private static Throwable recurse(int n) {
        if (n == 0) return new Throwable("recursive");
        return recurse(n - 1);
    }
    public static int recursion(int n) {
        last = recurse(n & 15);
        return answer(last, n);
    }
    public static int cause(int n) {
        Throwable root = new Throwable("root");
        Throwable outer = new Exception("outer", root);
        last = outer;
        return n + outer.getMessage().length() + (outer.getCause() == root ? 64 : 0);
    }
    public static int fillInStackTrace(int n) {
        last = new Throwable("named");
        return answer(last, n);
    }
    public static int lambda(int n) {
        Supplier<Throwable> factory = () -> new IllegalStateException("lambda");
        last = factory.get();
        return answer(last, n);
    }
    public static int noMessage(int n) {
        last = new Throwable();
        return n + (last.getMessage() == null ? 8 : 0) + (last.getCause() == null ? 16 : 0);
    }
    public static int reusable(int n) {
        if (held == null) held = new Throwable("reused");
        if (n != 0) held.fillInStackTrace();
        last = held;
        return n + held.getMessage().length();
    }
    public static int parallel(int n) {
        Throwable value = make(n);
        return answer(value, n);
    }
    public static int throwing(int n) { throw new IllegalStateException("not-yet-catchable"); }
    public static int caught(int n) {
        try { return 100 / n; }
        catch (ArithmeticException value) { return 19; }
    }
}
