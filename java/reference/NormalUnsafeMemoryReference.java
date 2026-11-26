import jdk.internal.misc.Unsafe;
import java.nio.file.*;
import java.util.*;

// Development JVM oracle only. Numeric offsets and object pointers stay local.
public final class NormalUnsafeMemoryReference {
    static final Unsafe U=Unsafe.getUnsafe();
    static final class Box { boolean z;byte b;char c;short s;int i;long j;float f;double d;Object r; }
    static final String[] NAMES={"","z","b","c","s","i","j","f","d","r"};
    static final long[] OFFSETS=new long[10];
    static {for(int i=1;i<=9;i++)OFFSETS[i]=U.objectFieldOffset(Box.class,NAMES[i]);}
    static Object array(int kind){return switch(kind){case 1->new boolean[4];case 2->new byte[32];case 3->new char[4];case 4->new short[4];case 5->new int[4];case 6->new long[4];case 7->new float[4];case 8->new double[4];default->new Object[4];};}
    static String hex(long n){return String.format(Locale.ROOT,"%016x",n);}
    static void put(int k,boolean v,Object o,long p,long n) {
        switch(k){
            case 1->{if(v)U.putBooleanVolatile(o,p,(n&1)!=0);else U.putBoolean(o,p,(n&1)!=0);}
            case 2->{if(v)U.putByteVolatile(o,p,(byte)n);else U.putByte(o,p,(byte)n);}
            case 3->{if(v)U.putCharVolatile(o,p,(char)n);else U.putChar(o,p,(char)n);}
            case 4->{if(v)U.putShortVolatile(o,p,(short)n);else U.putShort(o,p,(short)n);}
            case 5->{if(v)U.putIntVolatile(o,p,(int)n);else U.putInt(o,p,(int)n);}
            case 6->{if(v)U.putLongVolatile(o,p,n);else U.putLong(o,p,n);}
            case 7->{float f=Float.intBitsToFloat((int)n);if(v)U.putFloatVolatile(o,p,f);else U.putFloat(o,p,f);}
            case 8->{double d=Double.longBitsToDouble(n);if(v)U.putDoubleVolatile(o,p,d);else U.putDouble(o,p,d);}
            default->throw new AssertionError();
        }
    }
    static long get(int k,boolean v,Object o,long p){return switch(k){
        case 1->(v?U.getBooleanVolatile(o,p):U.getBoolean(o,p))?1:0;
        case 2->v?U.getByteVolatile(o,p):U.getByte(o,p);
        case 3->v?U.getCharVolatile(o,p):U.getChar(o,p);
        case 4->v?U.getShortVolatile(o,p):U.getShort(o,p);
        case 5->v?U.getIntVolatile(o,p):U.getInt(o,p);
        case 6->v?U.getLongVolatile(o,p):U.getLong(o,p);
        case 7->Integer.toUnsignedLong(Float.floatToRawIntBits(v?U.getFloatVolatile(o,p):U.getFloat(o,p)));
        case 8->Double.doubleToRawLongBits(v?U.getDoubleVolatile(o,p):U.getDouble(o,p));
        default->throw new AssertionError();};}
    public static void main(String[] args)throws Exception {
        List<String> input=Files.readAllLines(Path.of(args[0]));Box box=new Box();Object[] arrays=new Object[10];for(int k=1;k<=9;k++)arrays[k]=array(k);
        for(String line:input){
            String[] p=line.split("\t");int kind=Integer.parseInt(p[0]);long bits=Long.parseUnsignedLong(p[1],16);StringBuilder out=new StringBuilder(line);
            for(int storage=0;storage<2;storage++){
                Object target=storage==0?box:arrays[kind];long offset=storage==0?OFFSETS[kind]:U.arrayBaseOffset(target.getClass());
                for(boolean vol:new boolean[]{false,true}){put(kind,vol,target,offset,bits);out.append('\t').append(hex(get(kind,false,target,offset))).append('\t').append(hex(get(kind,true,target,offset)));}
            }
            System.out.println(out);
        }
        // Independent CAS/exchange reference and scalar relations.
        Object a=new Object(),b=new Object();Object[] refs={null,a,b};int atomic=0;
        for(int k:new int[]{5,6,9})for(int storage=0;storage<2;storage++)for(int initial=0;initial<3;initial++)for(int expected=0;expected<3;expected++)for(int desired=0;desired<3;desired++){
            Object target=storage==0?box:arrays[k];long offset=storage==0?OFFSETS[k]:U.arrayBaseOffset(target.getClass());
            if(k==9){U.putReference(target,offset,refs[initial]);boolean success=U.compareAndSetReference(target,offset,refs[expected],refs[desired]);if(success!=(initial==expected)||U.getReference(target,offset)!=refs[success?desired:initial])throw new AssertionError();U.putReference(target,offset,refs[initial]);if(U.compareAndExchangeReference(target,offset,refs[expected],refs[desired])!=refs[initial]||U.getReferenceVolatile(target,offset)!=refs[initial==expected?desired:initial])throw new AssertionError();}
            else if(k==5){U.putInt(target,offset,initial);boolean success=U.compareAndSetInt(target,offset,expected,desired);if(success!=(initial==expected)||U.getInt(target,offset)!=(success?desired:initial))throw new AssertionError();U.putInt(target,offset,initial);if(U.compareAndExchangeInt(target,offset,expected,desired)!=initial||U.getIntVolatile(target,offset)!=(initial==expected?desired:initial))throw new AssertionError();}
            else{U.putLong(target,offset,initial);boolean success=U.compareAndSetLong(target,offset,expected,desired);if(success!=(initial==expected)||U.getLong(target,offset)!=(success?desired:initial))throw new AssertionError();U.putLong(target,offset,initial);if(U.compareAndExchangeLong(target,offset,expected,desired)!=initial||U.getLongVolatile(target,offset)!=(initial==expected?desired:initial))throw new AssertionError();}
            atomic+=2;
        }
        byte[] bytes=new byte[32];long base=U.arrayBaseOffset(byte[].class);U.putLong(bytes,base+1,0x1234567876543210L);if(U.getLong(bytes,base+1)!=0x1234567876543210L)throw new AssertionError();
        U.putByte(box,OFFSETS[1],(byte)0xfe);if(!U.getBoolean(box,OFFSETS[1]))throw new AssertionError();
        System.err.println("atomic_cases\t"+atomic);System.err.println("unaligned_plain_cases\t1");System.err.println("boolean_nonzero_read_cases\t1");
    }
}
