package dev.boom.clone;

public final class CloneProgram {
    static int initialized;
    static int[] cached;

    // Bit 4 returns the source for native ABI tests; bit 5 selects an empty array.
    public static Object arrays(int selector) {
        int n = (selector & 32) == 0 ? 3 : 0;
        int seed = selector >>> 8;
        boolean source = (selector & 16) != 0;
        switch (selector & 15) {
            case 0: {
                boolean[] a = new boolean[n];
                if (n != 0) { a[0] = true; a[1] = (seed & 1) != 0; }
                return source ? a : a.clone();
            }
            case 1: {
                byte[] a = new byte[n];
                if (n != 0) { a[0] = (byte) seed; a[1] = -128; a[2] = 127; }
                return source ? a : a.clone();
            }
            case 2: {
                char[] a = new char[n];
                if (n != 0) { a[0] = (char) seed; a[1] = '\ud800'; a[2] = '\uffff'; }
                return source ? a : a.clone();
            }
            case 3: {
                short[] a = new short[n];
                if (n != 0) { a[0] = (short) seed; a[1] = -32768; a[2] = 32767; }
                return source ? a : a.clone();
            }
            case 4: {
                int[] a = new int[n];
                if (n != 0) { a[0] = seed; a[1] = Integer.MIN_VALUE; a[2] = -1; }
                return source ? a : a.clone();
            }
            case 5: {
                long[] a = new long[n];
                if (n != 0) { a[0] = ((long) seed << 32) | 0xabcdef01L; a[1] = Long.MIN_VALUE; a[2] = -1; }
                return source ? a : a.clone();
            }
            case 6: {
                float[] a = new float[n];
                if (n != 0) { a[0] = Float.intBitsToFloat(seed); a[1] = -0.0f; a[2] = Float.intBitsToFloat(0x7fc12345); }
                return source ? a : a.clone();
            }
            case 7: {
                double[] a = new double[n];
                if (n != 0) { a[0] = Double.longBitsToDouble(((long) seed << 32) | 0x12345678L); a[1] = -0.0; a[2] = Double.longBitsToDouble(0x7ff812345678abcdL); }
                return source ? a : a.clone();
            }
            case 8: {
                String[] a = new String[n];
                if (n != 0) { a[0] = "clone"; a[1] = "\u4e16\u754c\ud83d\ude80"; }
                return source ? a : a.clone();
            }
            case 9: {
                Class<?>[] a = new Class<?>[n];
                if (n != 0) { a[0] = CloneDormant.class; a[1] = int[].class; }
                return source ? a : a.clone();
            }
            default: {
                Object[] a = new Object[n];
                if (n != 0) { a[0] = new int[] {seed, ~seed}; a[1] = "shared"; }
                return source ? a : a.clone();
            }
        }
    }

    public static long checksum(int selector) {
        int kind = selector & 15;
        Object array = arrays(selector & ~16);
        if ((selector & 32) != 0) return 0;
        switch (kind) {
            case 0: { boolean[] a = (boolean[]) array; return (a[0] ? 1 : 0) + (a[1] ? 2 : 0); }
            case 1: { byte[] a = (byte[]) array; return a[0] + a[1] * 31L + a[2] * 997L; }
            case 2: { char[] a = (char[]) array; return a[0] + a[1] * 31L + a[2] * 997L; }
            case 3: { short[] a = (short[]) array; return a[0] + a[1] * 31L + a[2] * 997L; }
            case 4: { int[] a = (int[]) array; return a[0] + a[1] * 31L + a[2] * 997L; }
            case 5: { long[] a = (long[]) array; return a[0] + a[1] * 31 + a[2] * 997; }
            case 6: { float[] a = (float[]) array; return Integer.toUnsignedLong(Float.floatToRawIntBits(a[0])) ^ Integer.toUnsignedLong(Float.floatToRawIntBits(a[1])) ^ Integer.toUnsignedLong(Float.floatToRawIntBits(a[2])); }
            case 7: { double[] a = (double[]) array; return Double.doubleToRawLongBits(a[0]) ^ Double.doubleToRawLongBits(a[1]) ^ Double.doubleToRawLongBits(a[2]); }
            case 8: { String[] a = (String[]) array; return a[0].length() * 31 + a[1].length() + (a[2] == null ? 7 : 0); }
            case 9: { Class<?>[] a = (Class<?>[]) array; return (a[0] == CloneDormant.class ? 17 : 0) + (a[1] == int[].class ? 23 : 0) + initialized; }
            default: { Object[] a = (Object[]) array; int[] inner = (int[]) a[0]; return inner[0] * 31L + inner[1] + (a[2] == null ? 11 : 0); }
        }
    }

    public static int relations(int seed) {
        Object[] a = new Object[] { new int[] {seed, ~seed}, "shared", null };
        Object[] b = a.clone();
        int result = a != b && a.getClass() == b.getClass() ? 1 : 0;
        if (a[0] == b[0] && a[1] == b[1]) result += 2;
        ((int[]) b[0])[0] = seed + 1;
        if (((int[]) a[0])[0] == seed + 1) result += 4;
        b[1] = null;
        if (a[1] != null && b[1] == null) result += 8;
        Object[] covariant = new String[] {"a", "b"};
        Object[] c = covariant.clone();
        if (c.getClass() == String[].class && c != covariant) result += 16;
        try { c[0] = new Object(); } catch (ArrayStoreException expected) { result += 32; }
        int[] empty = new int[0];
        if (empty.clone() != empty && empty.clone().getClass() == int[].class) result += 64;
        if (((Class<?>[]) arrays(9))[0] == CloneDormant.class && initialized == 0) result += 128;
        return result;
    }

    public static int nullReceiver(int unused) {
        byte[] a = null;
        try { return a.clone().length; } catch (NullPointerException expected) { return 31; }
    }

    public static int fullHeap(int mode) {
        if (cached == null) cached = new int[] {17, 23, 31};
        if ((mode & 1) == 0) return cached.length;
        try { return cached.clone()[1]; } catch (OutOfMemoryError expected) { return 97; }
    }

    public static int parallel(int value) {
        int[] a = new int[] {value, ~value, value * 31};
        int[] b = a.clone();
        b[0] += 7;
        return b[0] ^ b[1] ^ b[2] ^ a[0];
    }
}

final class CloneDormant {
    static { CloneProgram.initialized += 7; }
}
