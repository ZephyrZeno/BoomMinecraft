import java.lang.reflect.Constructor;

// Independent development oracle: real JDK reflection performs every conversion.
public final class ConstructorWideningReference {
    static final Class<?>[] WRAPPERS={Boolean.class,Byte.class,Character.class,Short.class,
        Integer.class,Long.class,Float.class,Double.class};
    static final Class<?>[] PRIMITIVES={boolean.class,byte.class,char.class,short.class,
        int.class,long.class,float.class,double.class};
    static final long[][] VALUES={
        {0,1}, {-128,-1,0,1,127}, {0,1,127,255,32768,65535}, {-32768,-1,0,1,32767},
        {Integer.MIN_VALUE,Integer.MAX_VALUE,-1,0,1,16777215,16777217},
        {Long.MIN_VALUE,Long.MAX_VALUE,-1,0,1,16777217,9007199254740993L,Long.MAX_VALUE-1023},
        {0,0x80000000L,1,0x007fffff,0x00800000,0x3f800000,0xbf800000L,0x7f800000,0xff800000L,0x7fc12345,0x7f812345,0x7f7fffff},
        {0,0x8000000000000000L,1,0x000fffffffffffffL,0x0010000000000000L,0x3ff0000000000000L,
         0xbff0000000000000L,0x7ff0000000000000L,0xfff0000000000000L,0x7ff8123456789abcL,0x7ff0123456789abcL,0x7fefffffffffffffL}
    };
    static Object box(int k,long v) {
        return switch(k) {
            case 0 -> Boolean.valueOf((v&1)!=0);
            case 1 -> Byte.valueOf((byte)v);
            case 2 -> Character.valueOf((char)v);
            case 3 -> Short.valueOf((short)v);
            case 4 -> Integer.valueOf((int)v);
            case 5 -> Long.valueOf(v);
            case 6 -> Float.valueOf(Float.intBitsToFloat((int)v));
            case 7 -> Double.valueOf(Double.longBitsToDouble(v));
            default -> throw new AssertionError();
        };
    }
    static long bits(int k,Object value) {
        return switch(k) {
            case 0 -> ((Boolean)value)?1:0;
            case 1 -> Integer.toUnsignedLong(((Byte)value).intValue());
            case 2 -> ((Character)value).charValue();
            case 3 -> Integer.toUnsignedLong(((Short)value).intValue());
            case 4 -> Integer.toUnsignedLong(((Integer)value).intValue());
            case 5 -> ((Long)value).longValue();
            case 6 -> Integer.toUnsignedLong(Float.floatToRawIntBits(((Float)value).floatValue()));
            case 7 -> Double.doubleToRawLongBits(((Double)value).doubleValue());
            default -> throw new AssertionError();
        };
    }
    public static void main(String[] args) throws Exception {
        Constructor<?>[] constructors=new Constructor<?>[8];
        for(int k=0;k<8;k++)constructors[k]=WRAPPERS[k].getConstructor(PRIMITIVES[k]);
        for(int from=0;from<8;from++)for(long value:VALUES[from])for(int to=0;to<8;to++) {
            int status=0;long result=0;
            try {result=bits(to,constructors[to].newInstance(box(from,value)));}
            catch(IllegalArgumentException e) {status=18;}
            System.out.println(from+"\t"+to+"\t"+Long.toUnsignedString(value)+"\t"+status+"\t"+Long.toUnsignedString(result));
        }
    }
}
