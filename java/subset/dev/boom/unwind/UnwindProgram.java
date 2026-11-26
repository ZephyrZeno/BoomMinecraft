package dev.boom.unwind;

// JVM is the independent development oracle. The native image executes ASM only.
public final class UnwindProgram {
    public static Throwable last;
    public static Throwable first;
    public static int effects;
    public static Object lock;

    static final class Child extends IllegalArgumentException {
        Child(String message) { super(message); }
    }
    static final class BadInit {
        static int value = fail();
        static int fail() { effects++; throw new IllegalStateException("initializer-root"); }
    }
    static final class ErrorInit {
        static int value = fail();
        static int fail() { throw new AssertionError(); }
    }
    static final class NullBox { int value; }

    public static int arithmetic(int n) {
        try { return 100 / n; }
        catch (ArithmeticException e) {
            last = e;
            return e.getMessage().equals("/ by zero") && e.getCause() == null ? 19 : 0;
        }
    }
    public static int identity(int n) {
        IllegalStateException original = new IllegalStateException("identity");
        try { throw original; }
        catch (RuntimeException e) { last = e; return (e == original ? 100 : 0) + n; }
    }
    static void inner(Throwable e) throws Throwable { throw e; }
    public static int rethrow(int n) {
        Throwable original = new Child("child");
        int local = n + 31;
        try {
            try { inner(original); }
            catch (IllegalArgumentException e) { effects++; throw e; }
        } catch (Throwable e) { last = e; return local + (e == original ? 64 : 0); }
        return 0;
    }
    public static int ordered(int n) {
        try {
            if ((n & 1) == 0) throw new Child("child");
            throw new IllegalStateException("state");
        } catch (Child e) { last = e; return n + 1; }
        catch (IllegalArgumentException e) { return n + 2; }
        catch (RuntimeException e) { last = e; return n + 3; }
    }
    public static int multicatch(int n) {
        try {
            if ((n & 1) == 0) return (new int[n & 7])[9];
            return 7 / (n & 2);
        } catch (ArithmeticException | ArrayIndexOutOfBoundsException e) {
            last = e; return e instanceof ArithmeticException ? 41 : 43;
        }
    }
    public static int finallyPath(int n) {
        effects = 0;
        try {
            try { return 71 / n; }
            finally { effects += 5; }
        } catch (ArithmeticException e) { last = e; return effects + 91; }
    }
    public static int finallyRethrow(int n) {
        Throwable original = new IllegalStateException("finally");
        effects = 0;
        try {
            try { inner(original); }
            finally { effects = n + 7; }
        } catch (Throwable e) { last = e; return effects + (e == original ? 32 : 0); }
        return 0;
    }
    public static int throwNull(int n) {
        try { throw (RuntimeException)null; }
        catch (NullPointerException e) { last = e; return e.getMessage() != null ? n + 7 : 0; }
    }
    public static int implicitNpe(int n) {
        try {
            if ((n & 1) == 0) return ((NullBox)null).value;
            return ((int[])null).length;
        } catch (NullPointerException e) {
            last = e;
            String message = e.getMessage();
            return message != null && e.getMessage() == message && e.getCause() == null ? n + 17 : 0;
        }
    }
    public static int explicitNpe(int n) {
        NullPointerException original = new NullPointerException();
        try { throw original; }
        catch (NullPointerException e) { last = e; return e == original && e.getMessage() == null ? n + 23 : 0; }
    }
    public static int bounds(int n) {
        try { return (new int[3])[n]; }
        catch (ArrayIndexOutOfBoundsException e) { last = e; return n + 47; }
    }
    public static int negativeArray(int n) {
        try { return new int[n | 0x80000000].length; }
        catch (NegativeArraySizeException e) { last = e; return n + 53; }
    }
    public static int arrayStore(int n) {
        Object[] array = new String[1];
        try { array[0] = new Object(); return 0; }
        catch (ArrayStoreException e) { last = e; return n + 59; }
    }
    public static int cast(int n) {
        Object value = new Object();
        try { return ((String)value).length(); }
        catch (ClassCastException e) { last = e; return n + 61; }
    }
    public static int monitor(int n) {
        Object value = new Object();
        effects = 0;
        try {
            synchronized (value) {
                synchronized (value) { effects = 3; return 80 / n; }
            }
        } catch (ArithmeticException e) {
            last = e;
            synchronized (value) { effects += 5; }
            return effects + 100;
        }
    }
    public static int nullMonitor(int n) {
        try { synchronized ((Object)null) { return 0; } }
        catch (NullPointerException e) { last = e; return e.getMessage() != null ? n + 67 : 0; }
    }
    static synchronized int synchronizedThrow(int n) { return 103 / n; }
    public static int synchronizedMethod(int n) {
        try { return synchronizedThrow(n); }
        catch (ArithmeticException e) { last = e; return synchronizedThrow(1) + n; }
    }
    public static int initFailure(int n) {
        try { return BadInit.value; }
        catch (ExceptionInInitializerError e) {
            last = first = e;
            return e.getException() instanceof IllegalStateException && e.getException() == e.getCause() ? n + 71 : 0;
        } catch (NoClassDefFoundError e) {
            last = e; return e.getCause() instanceof ExceptionInInitializerError ? n + 73 : 0;
        }
    }
    public static int initError(int n) {
        try { return ErrorInit.value; }
        catch (AssertionError e) { last = first = e; return n + 79; }
        catch (NoClassDefFoundError e) { last = e; return n + 83; }
    }
    public static int initParallel(int n) {
        try { return BadInit.value; }
        catch (ExceptionInInitializerError e) { return 71; }
        catch (NoClassDefFoundError e) { return 73; }
    }
    public static int oom(int n) {
        try { return new int[Integer.MAX_VALUE].length; }
        catch (OutOfMemoryError e) { last = e; return n + 89; }
    }
    static int recurse(int n) { return recurse(n + 1) + 1; }
    public static int stackOverflow(int n) {
        try { return recurse(n); }
        catch (StackOverflowError e) { last = e; return n + 97; }
    }
    public static int uncaught(int n) { throw new Child("uncaught"); }
    public static int parallel(int n) {
        try {
            synchronized (UnwindProgram.class) {
                if ((n & 3) == 0) throw new IllegalArgumentException("parallel");
                return 97 / (n & 1);
            }
        } catch (IllegalArgumentException e) { return n + 101; }
        catch (ArithmeticException e) { return n + 103; }
    }
}
