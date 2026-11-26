package dev.boom.initialization;
import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.FileOutputStream;
/** Discovery only until the complete Java stream constructor chain is supported. */
public final class StreamConstruction {
    public static int input(int n) {
        FileInputStream stream = new FileInputStream(FileDescriptor.in);
        return stream == null ? n : n + 1;
    }
    public static int output(int n) {
        FileOutputStream stream = new FileOutputStream(FileDescriptor.out);
        return stream == null ? n : n + 1;
    }
}
