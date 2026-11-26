package dev.boom.sequence;
public final class OpaqueCtorLookup {
 public static int run(int initialize)throws Exception {Class<?> known=java.lang.reflect.Constructor.class;return Class.forName("java.lang.reflect.Constructor",initialize!=0,null)==known?1:0;}
}
