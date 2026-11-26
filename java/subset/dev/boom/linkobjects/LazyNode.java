package dev.boom.linkobjects;
public final class LazyNode {
    public int value;
    static {InitMarker.runs++;}
    public LazyNode(int value) {this.value=value;}
}
