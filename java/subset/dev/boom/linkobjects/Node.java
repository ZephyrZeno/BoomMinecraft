package dev.boom.linkobjects;
public final class Node {
    public Node next;
    public Box box;
    public Node[] children;
    public int[] numbers;
    public Node(Box box) {this.box=box;box.owner=this;}
    public int value(int add) {return box.mix(add);}
    public Node link(Node other) {next=other;return this;}
}
