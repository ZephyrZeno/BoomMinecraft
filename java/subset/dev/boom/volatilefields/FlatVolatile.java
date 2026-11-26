package dev.boom.volatilefields;
public final class FlatVolatile {
    volatile int value;
    volatile byte narrow;
    public static int roundtrip(int input) {
        FlatVolatile object=new FlatVolatile();
        object.value=input;object.narrow=(byte)input;
        return object.value+object.narrow;
    }
}
