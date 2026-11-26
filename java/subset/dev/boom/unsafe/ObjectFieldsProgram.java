package dev.boom.unsafe;
import jdk.internal.misc.Unsafe;
import java.lang.reflect.Field;
public final class ObjectFieldsProgram {
    static class Parent {
        boolean flag;
        byte narrow = -128;
        int counter = 17;
        long wide = 19;
        static boolean shared;
    }
    static final class Child extends Parent {
        Object reference = "anchor";
        int counter = 99;
        boolean other;
    }
    static final class More extends Parent { Object first = "first", second = "second"; }
    static int initialized;
    static class Cold { boolean flag; static { initialized++; } }
    static final Unsafe U = Unsafe.getUnsafe();
    static final long FLAG = U.objectFieldOffset(Parent.class, "flag");
    static final Child SHARED = new Child();
    public static String run(int mode) throws Exception {
        if (mode == 0) {
            Parent p = new Parent();
            return U.getBooleanVolatile(p,FLAG)+":"+U.compareAndSetBoolean(p,FLAG,false,true)+":"+U.getBooleanVolatile(p,FLAG)+":"+U.compareAndSetBoolean(p,FLAG,false,true)+":"+p.flag;
        }
        if (mode == 1) {
            Child p = new Child();U.compareAndSetBoolean(p,FLAG,false,true);
            return p.flag+":"+p.other+":"+((Parent)p).counter+":"+p.counter+":"+p.wide+":"+(p.reference=="anchor");
        }
        if (mode == 2) {
            Child p = new Child();long offset=U.objectFieldOffset(Parent.class,"counter");
            int old=U.getAndAddInt(p,offset,1);boolean changed=U.compareAndSetInt(p,offset,18,-1);
            return old+":"+changed+":"+U.getIntVolatile(p,offset)+":"+((Parent)p).counter+":"+p.counter;
        }
        if (mode == 3) {
            More p = new More();long offset=U.objectFieldOffset(Parent.class,"wide");
            boolean changed=U.compareAndSetLong(p,offset,19,Long.MIN_VALUE);
            return changed+":"+U.getLongVolatile(p,offset)+":"+p.wide+":"+(p.first=="first")+":"+(p.second=="second");
        }
        if (mode == 4 || mode == 5) {
            try { U.objectFieldOffset(mode==4?Child.class:Parent.class,mode==4?"flag":"missing");return "missing-error"; }
            catch (InternalError error) { return error.getMessage()==null?"internal-null":"internal-message"; }
        }
        if (mode == 6 || mode == 7) {
            try { U.objectFieldOffset(mode==6?null:Parent.class,mode==7?null:"flag");return "missing-error"; }
            catch (NullPointerException expected) { return "null"; }
        }
        if (mode == 8) { U.objectFieldOffset(Cold.class,"flag");return initialized==0?"cold":"initialized"; }
        if (mode == 9) {
            boolean[] flags = new boolean[3];long base=U.arrayBaseOffset(boolean[].class),scale=U.arrayIndexScale(boolean[].class);
            return U.getBooleanVolatile(flags,base)+":"+U.compareAndSetBoolean(flags,base,false,true)+":"+U.getBooleanVolatile(flags,base)+":"+flags[0]+":"+flags[1]+":"+scale;
        }
        if (mode == 10) {
            Field f=Parent.class.getDeclaredField("shared");Object base=U.staticFieldBase(f);long offset=U.staticFieldOffset(f);
            boolean first=U.compareAndSetBoolean(base,offset,false,true);boolean value=U.getBooleanVolatile(base,offset);
            U.compareAndSetBoolean(base,offset,true,false);
            return first+":"+value+":"+(offset==U.objectFieldOffset(Parent.class,"shared"));
        }
        if (mode == 11) {
            try { U.objectFieldOffset(Parent.class,"flag\0");return "missing-error"; }
            catch (InternalError error) { return error.getMessage()==null?"internal-null":"internal-message"; }
        }
        if (mode == 12) {
            long offset=U.objectFieldOffset(ClassLoader.class,"defaultAssertionStatus");
            return offset==U.objectFieldOffset(ClassLoader.class,"defaultAssertionStatus")?"filtered-offset":"unstable";
        }
        if (mode == 13) {
            try { ClassLoader.class.getDeclaredField("defaultAssertionStatus");return "visible"; }
            catch (NoSuchFieldException expected) { return "filtered"; }
        }
        if (mode == 14) return U.objectFieldOffset(Parent.class,"flag")==FLAG?"stable":"unstable";
        if (mode == 15) return SHARED.reference=="anchor"?"rooted":"missing";
        if (mode == 16) { SHARED.flag=false;return "reset"; }
        if (mode == 18) {
            Parent p=new Parent();long offset=U.objectFieldOffset(Parent.class,"narrow");
            byte first=U.compareAndExchangeByte(p,offset,(byte)-128,(byte)127),second=U.compareAndExchangeByte(p,offset,(byte)-128,(byte)0);
            byte[] bytes={(byte)-128,0};long base=U.arrayBaseOffset(byte[].class);
            byte third=U.compareAndExchangeByte(bytes,base,(byte)-128,(byte)-1),fourth=U.compareAndExchangeByte(bytes,base,(byte)0,(byte)1);
            return first+":"+second+":"+p.narrow+":"+third+":"+fourth+":"+bytes[0]+":"+bytes[1];
        }
        return U.compareAndSetBoolean(SHARED,FLAG,false,true)?"won":"lost";
    }
}
