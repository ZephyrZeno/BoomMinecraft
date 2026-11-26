package dev.boom.unsafe;

import jdk.internal.misc.Unsafe;

public final class LongAtomic {
    public static long apply(long[] array, int index, long expected, long delta, int operation) {
        Unsafe unsafe = Unsafe.getUnsafe();
        long offset = Unsafe.ARRAY_LONG_BASE_OFFSET + (long) index * Unsafe.ARRAY_LONG_INDEX_SCALE;
        if (operation == 0) return unsafe.getLongVolatile(array, offset);
        if (operation == 1 || operation == 3)
            return unsafe.compareAndSetLong(array, offset, expected, delta) ? 1 : 0;
        return unsafe.getAndAddLong(array, offset, delta);
    }
}
