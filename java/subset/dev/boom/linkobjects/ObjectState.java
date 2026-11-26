package dev.boom.linkobjects;
public final class ObjectState {
    public static final Node root;
    public static Node alias;
    static {root=ObjectOps.node(17);Node second=ObjectOps.node(23);root.next=second;second.next=root;root.children=ObjectOps.array(2);root.children[0]=second;root.children[1]=root;root.numbers=new int[11];alias=root;}
}
