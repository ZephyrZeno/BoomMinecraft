package dev.boom.initialization;
import java.io.FileDescriptor;
import jdk.internal.access.JavaIOFileDescriptorAccess;
import jdk.internal.access.SharedSecrets;

/** Development fixture: the first active request must enter the original lazy getter. */
public final class InitializationEntry {
    public static int lazy(int n) {
        JavaIOFileDescriptorAccess access = SharedSecrets.getJavaIOFileDescriptorAccess();
        int result = n + access.get(FileDescriptor.in) + access.get(FileDescriptor.out) + access.get(FileDescriptor.err);
        return result + (access == SharedSecrets.getJavaIOFileDescriptorAccess() ? 8 : 0)
            + (access.getAppend(FileDescriptor.out) ? 16 : 0);
    }
    public static int handles(int n) {
        JavaIOFileDescriptorAccess access = SharedSecrets.getJavaIOFileDescriptorAccess();
        return n + (access.getHandle(FileDescriptor.in) == -1 ? 0 : 1)
            + (access.getHandle(FileDescriptor.out) == -1 ? 0 : 2)
            + (access.getHandle(FileDescriptor.err) == -1 ? 0 : 4);
    }
}
