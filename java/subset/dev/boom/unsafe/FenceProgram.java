package dev.boom.unsafe;
import jdk.internal.misc.Unsafe;
public final class FenceProgram {
    static int x, y;
    public static int run(int slot) {
        Unsafe unsafe = Unsafe.getUnsafe();
        if (slot == 0) { x = 1; unsafe.fullFence(); return y; }
        if (slot == 1) { y = 1; unsafe.fullFence(); return x; }
        x = 0; y = 0; return 0;
    }
}
