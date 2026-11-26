import java.util.Random;

// JVM oracle only. Never part of the delivered assembly runtime.
public final class FloatingRemainderReference {
    static void f(int a, int b) {
        int result=Float.floatToIntBits(Float.intBitsToFloat(a)%Float.intBitsToFloat(b));
        System.out.println("F\t"+Integer.toUnsignedString(a,16)+"\t"+Integer.toUnsignedString(b,16)+"\t"+Integer.toUnsignedString(result,16));
    }
    static void d(long a,long b) {
        long result=Double.doubleToLongBits(Double.longBitsToDouble(a)%Double.longBitsToDouble(b));
        System.out.println("D\t"+Long.toUnsignedString(a,16)+"\t"+Long.toUnsignedString(b,16)+"\t"+Long.toUnsignedString(result,16));
    }
    public static void main(String[] args) {
        int[] floats={0,0x80000000,1,0x80000001,0x007fffff,0x00800000,0x00800001,0x3f000000,0x3f800000,0x40000000,0x40400000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc00000,0x7f800001};
        long[] doubles={0,0x8000000000000000L,1,0x8000000000000001L,0xfffffffffffffL,0x10000000000000L,0x10000000000001L,0x3fe0000000000000L,0x3ff0000000000000L,0x4000000000000000L,0x4008000000000000L,0x7fefffffffffffffL,0xffefffffffffffffL,0x7ff0000000000000L,0xfff0000000000000L,0x7ff8000000000000L,0x7ff0000000000001L};
        for(int a:floats)for(int b:floats)f(a,b);
        for(long a:doubles)for(long b:doubles)d(a,b);
        Random random=new Random(0x6f2d43b17a90L);
        for(int i=0;i<50000;i++){f(random.nextInt(),random.nextInt());d(random.nextLong(),random.nextLong());}
    }
}
