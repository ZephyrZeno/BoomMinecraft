package dev.boom.records;

record Dollar$Record(int value) {}
public final class RecordProgram {
    record Point(int x, long y, boolean yes, char ch, String name) {}
    record Empty() {}
    record Small(byte value, short other) {}
    record Accessor(int value) { public int value() { return 999; } }
    record Unicode(int 数量) {}
    public static String run(int mode) {
        if (mode == 0) return new Point(1,2L,true,'A',"text").toString();
        if (mode == 1) return new Point(Integer.MIN_VALUE,Long.MIN_VALUE,false,'\uffff',"name").toString();
        if (mode == 2) return new Point(-1,-17L,true,'\ud800',"\udc00x").toString();
        if (mode == 3) return new Empty().toString();
        if (mode == 4) return new Empty().toString() == new Empty().toString() ? "same" : "different";
        if (mode == 5) { record Local$Record(int value) {} return new Local$Record(9).toString(); }
        if (mode == 6) return new Dollar$Record(7).toString();
        if (mode == 7) return new Unicode(42).toString();
        if (mode == 8) return new Small((byte)-128,(short)-32768).toString();
        if (mode == 9) return new Accessor(3).toString();
        if (mode == 10) return new Point(0,0L,false,'\0',null).toString();
        return new Point(123,456L,true,'x',"").toString();
    }
}
