package dev.boom.volatilefields;

public final class VolatileEntry {
    static final Cell cell = new Cell();
    static volatile int x;
    // Keep the two store-buffering locations on distinct cache lines under the
    // current eight-byte static-slot ABI. These are ordinary Java fields.
    static long p0,p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12,p13,p14,p15;
    static volatile int y;
    static int payload;
    static volatile int ready;
    static volatile Payload published;
    static volatile long wide;
    static volatile double decimal;
    static volatile String text;
    static final long A = 0x12345678abcdef01L, B = 0xfedcba9876543210L;
    public static int byteValue(int value) { cell.b=(byte)value; return cell.b; }
    public static int booleanValue(int value) { cell.z=(value&1)!=0; return cell.z?1:0; }
    public static int shortValue(int value) { cell.s=(short)value; return cell.s; }
    public static int charValue(int value) { cell.c=(char)value; return cell.c; }
    public static int intValue(int value) { cell.i=value; return cell.i; }
    public static long longValue(long value) { cell.l=value; return cell.l; }
    public static float floatValue(float value) { cell.f=value; return cell.f; }
    public static double doubleValue(double value) { cell.d=value; return cell.d; }
    public static long staticLong(long value) { wide=value; return wide; }
    public static double staticDouble(double value) { decimal=value; return decimal; }
    public static int reference(int value) { cell.ref=new Payload(value); return cell.ref.value; }
    public static int staticReference(int value) { published=new Payload(value); return published.value; }
    public static int neighbors(int a,int b) { cell.b=(byte)a;cell.adjacent=(byte)b;return cell.b*257+cell.adjacent; }
    public static int stringValue(int value) { text=(value&1)==0?"one":"longer";return text.length(); }
    public static int arrayValue(int value) { cell.array=new int[1];cell.array[0]=value;return cell.array[0]; }
    public static int nullRead(int ignored) { Cell value=null;return value.i; }
    // One entry selects actors, so both threads use exactly the same generated
    // module, heap and static cells. The native harness supplies per-thread contexts.
    public static long actor(int mode) {
        switch(mode) {
            case 0: x=0;y=0;return 0;
            case 1: x=1;return y;
            case 2: y=1;return x;
            case 3: cell.x=0;cell.y=0;return 0;
            case 4: cell.x=1;return cell.y;
            case 5: cell.y=1;return cell.x;
            case 6: payload=0;ready=0;return 0;
            case 7: payload=0x12345678;ready=1;return 0;
            case 8: {
                int attempts=0;
                while(ready==0 && attempts++<100000000) {}
                return ready==0?-2:payload;
            }
            case 9: published=null;return 0;
            case 10: published=new Payload(0x12345678);return 0;
            case 11: {
                int attempts=0;Payload found;
                while((found=published)==null && attempts++<100000000) {}
                if(found==null)return -2;
                return found.value==0x12345678 && found.wide==A?0x12345678:-3;
            }
            case 12: wide=A;return 0;
            case 13: for(int i=0;i<100;i++)wide=(i&1)==0?A:B;return 0;
            case 14: for(int i=0;i<100;i++){long value=wide;if(value!=A&&value!=B)return -4;}return 0;
            case 15: cell.b=0;cell.adjacent=0;return 0;
            case 16: for(int i=0;i<128;i++)cell.b=(byte)i;return 0;
            case 17: for(int i=0;i<128;i++)cell.adjacent=(byte)(-i);return 0;
            case 18: return cell.z?-5:cell.b*257+cell.adjacent;
            default: return -1;
        }
    }
}
class Base {
    volatile Payload ref;
    volatile int[] array;
    volatile long l;
    volatile double d;
    volatile int i,x,y;
    volatile float f;
    volatile short s;
    volatile char c;
    volatile byte b;
    volatile boolean z;
}
final class Cell extends Base { volatile byte adjacent; }
final class Payload {
    int value;
    long wide;
    Payload(int value) { this.value=value;this.wide=VolatileEntry.A; }
}
