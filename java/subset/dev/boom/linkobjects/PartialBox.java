package dev.boom.linkobjects;
public final class PartialBox {
    public int value;
    public int[] values;
    public PartialBox(int divisor) {ConstructorState.partial=this;values=new int[3];value=11/divisor;}
}
