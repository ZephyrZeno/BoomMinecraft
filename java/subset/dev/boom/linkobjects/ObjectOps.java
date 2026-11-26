package dev.boom.linkobjects;
public final class ObjectOps {
    public static Box box(int value) {return new Box(value);}
    public static Node node(int value) {return new Node(box(value));}
    public static int read(Node node,int add) {return node.value(add);}
    public static Node[] array(int count) {return new Node[count];}
    public static int sum(Node[] nodes) {int result=0;for(int i=0;i<nodes.length;i++)if(nodes[i]!=null)result+=read(nodes[i],i);return result;}
}
