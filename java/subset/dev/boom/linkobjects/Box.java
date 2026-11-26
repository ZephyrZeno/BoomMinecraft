package dev.boom.linkobjects;
public final class Box {
    public final int value;
    public Node owner;
    public long wide;
    public float single;
    public double decimal;
    public byte tiny;
    public char character;
    public short small;
    public boolean flag;
    public Box(int value) {this.value=value;wide=(long)value*123456789;single=(float)value/3;decimal=(double)value/7;tiny=(byte)value;character=(char)value;small=(short)value;flag=(value&1)!=0;}
    public int mix(int add) {return value+add+tiny+character+small+(flag?17:0);}
    public long wideValue() {return wide+(long)single+(long)decimal;}
    public double decimalValue() {return decimal+(double)single;}
}
