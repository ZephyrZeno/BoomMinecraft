import java.io.DataOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import jdk.internal.misc.Unsafe;

public final class UnsafeBootstrapReference {
    public static void main(String[] args) throws Exception {
        if (args[0].equals("bad")) {
            Class.forName("dev.boom.unsafe.BadRegistration").getMethod("run").invoke(null);
            throw new AssertionError("Private native access unexpectedly succeeded");
        }
        Unsafe unsafe = Unsafe.getUnsafe();
        long[] edges = {0, 1, -1, Long.MIN_VALUE, Long.MAX_VALUE, 0x123456789abcdefL};
        long state = 0x7182e34a5b6c7d89L;
        try (var out = new DataOutputStream(Files.newOutputStream(Path.of(args[0])))) {
            for (int i = 0; i < 1024; i++) {
                state = state * 6364136223846793005L + 1442695040888963407L;
                long start = i < edges.length * edges.length ? edges[i / edges.length] : state;
                long delta = i < edges.length * edges.length ? edges[i % edges.length] : Long.rotateLeft(state, 17);
                int operation = i % 4;
                int index = (i / 4) % 4;
                long expected = operation == 3 ? start ^ 1 : start;
                long[] array = new long[4];
                array[index] = start;
                long offset = unsafe.arrayBaseOffset(long[].class) + (long) index * unsafe.arrayIndexScale(long[].class);
                long result = operation == 0 ? unsafe.getLongVolatile(array, offset)
                    : operation == 2 ? unsafe.getAndAddLong(array, offset, delta)
                    : unsafe.compareAndSetLong(array, offset, expected, delta) ? 1 : 0;
                out.writeInt(operation); out.writeInt(index); out.writeLong(start);
                out.writeLong(expected); out.writeLong(delta); out.writeLong(result); out.writeLong(array[index]);
            }
        }
    }
}
