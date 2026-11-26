import java.nio.*;
import java.util.LinkedHashSet;

// JVM oracle only. No Java process participates in native game execution.
public final class BufferDispatchReference {
    private static final LinkedHashSet<String> seen = new LinkedHashSet<>();
    private static void emit(Buffer b) {
        String line=b.getClass().getName().replace('.','/')+"\t"+(b.isDirect()?1:0)+"\t"+(b.isReadOnly()?1:0);
        if(seen.add(line)) System.out.println(line);
    }
    private static void views(ByteBuffer b) {
        emit(b);emit(b.asReadOnlyBuffer());emit(b.duplicate());emit(b.slice());
        CharBuffer c=b.asCharBuffer();emit(c);emit(c.asReadOnlyBuffer());
        ShortBuffer s=b.asShortBuffer();emit(s);emit(s.asReadOnlyBuffer());
        IntBuffer i=b.asIntBuffer();emit(i);emit(i.asReadOnlyBuffer());
        LongBuffer l=b.asLongBuffer();emit(l);emit(l.asReadOnlyBuffer());
        FloatBuffer f=b.asFloatBuffer();emit(f);emit(f.asReadOnlyBuffer());
        DoubleBuffer d=b.asDoubleBuffer();emit(d);emit(d.asReadOnlyBuffer());
    }
    public static void main(String[] args) {
        for(ByteOrder order:new ByteOrder[]{ByteOrder.BIG_ENDIAN,ByteOrder.LITTLE_ENDIAN}) {
            views(ByteBuffer.allocate(64).order(order));
            views(ByteBuffer.allocateDirect(64).order(order));
        }
        CharBuffer c=CharBuffer.allocate(8);emit(c);emit(c.asReadOnlyBuffer());
        ShortBuffer s=ShortBuffer.allocate(8);emit(s);emit(s.asReadOnlyBuffer());
        IntBuffer i=IntBuffer.allocate(8);emit(i);emit(i.asReadOnlyBuffer());
        LongBuffer l=LongBuffer.allocate(8);emit(l);emit(l.asReadOnlyBuffer());
        FloatBuffer f=FloatBuffer.allocate(8);emit(f);emit(f.asReadOnlyBuffer());
        DoubleBuffer d=DoubleBuffer.allocate(8);emit(d);emit(d.asReadOnlyBuffer());
    }
}
