package dev.boom.subset;

/** Source fixtures, compiled by javac; kernels themselves run from generated ASM. */
public final class IntKernels {
    public static int constant() { return Integer.MIN_VALUE; }
    public static int mix(int a, int b) { return ((a * 31 + b) ^ (a >>> 13)) - (b & 255); }
    public static int signedCompare(int a, int b) { if (a < b) return -1; if (a > b) return 1; return 0; }
    public static int abs(int a) { if (a < 0) return -a; return a; }
    public static int shifts(int value, int count) { return (value << count) ^ (value >> count) ^ (value >>> count); }
    public static int sumTo(int n) { int sum = 0; for (int i = 0; i < n; i++) sum += i; return sum; }
    public static int choose(int a, int b, int mask) { int value; if ((mask & 1) == 0) value = a; else value = b; return value * 3 + (mask >>> 2); }
    public static int nested(int n, int m) { int result = 0; for (int i = 0; i < n; i++) for (int j = 0; j < m; j++) result ^= i * 31 + j; return result; }
    public static int bump(int value) { value += 30000; value -= 30000; return value; }
    public static int four(int a, int b, int c, int d) { return (a ^ b) + c * d; }
    public static int fib(int n) { int a = 0; int b = 1; for (int i = 0; i < n; i++) { int next = a + b; a = b; b = next; } return a; }
    public static int denseSwitch(int value) { return switch (value) { case -2 -> 17; case -1 -> -3; case 0 -> 42; case 1 -> 99; case 2 -> 8; default -> value ^ 7; }; }
    public static int sparseSwitch(int value) { return switch (value) { case Integer.MIN_VALUE -> 1; case -701 -> 5; case 30000 -> 11; case Integer.MAX_VALUE -> -17; default -> value + 13; }; }
    public static int callChain(int a, int b, int c, int d) { return mix(a, b) + four(d, c, b, a) - abs(c); }
    public static int nestedCalls(int value) { return callChain(value, 7, -9, 31) ^ mix(abs(value), denseSwitch(value)); }
    public static int parallelWork(int value, int seed, int mask, int steps) { for (int i = 0; i < steps; i++) value = ((value * 1664525 + seed) ^ (value >>> 13)) + (i & mask); return value; }
    public static int recursive(int n) { if (n <= 0) return 0; return recursive(n - 1) + n; }

    // These must be rejected; they are not implemented by i32-v1.
    public static int divide(int a, int b) { return a / b; }
    public static int calls(int a) { return Math.abs(a); }
    public static synchronized int monitor(int a) { return a; }
    public static int allocation(int a) { return new int[] {a}[0]; }
    public static int handler(int a, int b) { try { return a / b; } catch (ArithmeticException error) { return -1; } }
}
