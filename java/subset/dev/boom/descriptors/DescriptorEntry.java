package dev.boom.descriptors;
import java.io.FileDescriptor;
public final class DescriptorEntry {
    public static int standard(int n) {
        return n+(FileDescriptor.in.valid()?1:0)+(FileDescriptor.out.valid()?2:0)+(FileDescriptor.err.valid()?4:0);
    }
    public static int fresh(int n) {
        FileDescriptor a=new FileDescriptor(),b=new FileDescriptor();
        return n+(a==b?1:0)+(a.valid()?2:0)+(b.valid()?4:0);
    }
    public static int identity(int n) {
        return n+(FileDescriptor.in==FileDescriptor.out?1:0)+(FileDescriptor.out==FileDescriptor.err?2:0)+(FileDescriptor.in==FileDescriptor.in?4:0);
    }
    private static final class Box {
        private final int value;
        private Box(int n){value=n;}
    }
    private static final class Reader {
        static int read(Box b){return b.value;}
    }
    public static int nested(int n){return Reader.read(new Box(n));}
}
