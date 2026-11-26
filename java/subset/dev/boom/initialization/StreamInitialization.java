package dev.boom.initialization;
import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.FileOutputStream;
/** Static subclass entry triggers the real superclass initializer; no constructor is invoked. */
public final class StreamInitialization {
    public static final class Input extends FileInputStream {
        private Input() { super(FileDescriptor.in); }
        public static int run(int n) { return n + 1; }
    }
    public static final class Output extends FileOutputStream {
        private Output() { super(FileDescriptor.out); }
        public static int run(int n) { return n + 2; }
    }
}
