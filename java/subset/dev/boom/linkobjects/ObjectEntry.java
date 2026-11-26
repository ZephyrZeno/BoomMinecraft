package dev.boom.linkobjects;
public final class ObjectEntry {
    public static int pair(int value,int add) {return ObjectOps.read(ObjectOps.node(value),add);}
    public static long wide(int value) {return ObjectOps.box(value).wideValue();}
    public static double decimal(int value) {return ObjectOps.box(value).decimalValue();}
    public static int graph(int value,int count) {
        Node first=ObjectOps.node(value),second=ObjectOps.node(value+1);first.link(second);second.link(first);
        first.numbers=new int[count];first.children=ObjectOps.array(2);first.children[0]=first;first.children[1]=second;
        for(int i=0;i<count;i++)first.numbers[i]=value+i;
        return first.next.box.owner.next.value(count)^first.children[1].value(value)^first.numbers.length;
    }
    public static int arrays(int count,int index) {
        Node[] nodes=ObjectOps.array(count);for(int i=0;i<count;i++)nodes[i]=ObjectOps.node(i*3);
        return nodes[index].value(index)^ObjectOps.sum(nodes);
    }
    public static int nullField(int value) {Node node=value<0?null:ObjectOps.node(value);return node.box.value;}
    public static int nullStore(int value) {Node node=value<0?null:ObjectOps.node(value);node.box=null;return node.box==null?1:0;}
    public static int nullCall(int value) {Node node=value<0?null:ObjectOps.node(value);return ObjectOps.read(node,3);}
    public static int nullElement(int count,int index) {return ObjectOps.array(count)[index].value(7);}
    public static int nullArray(int index) {Node[] nodes=null;return nodes[index].value(7);}
    public static int nullArrayStore(int index) {Node[] nodes=null;nodes[index]=null;return 1;}
    public static int lazyArray(int count) {LazyNode[] nodes=new LazyNode[count];return nodes.length+InitMarker.runs*1000;}
    public static int lazyObject(int value) {return new LazyNode(value).value+InitMarker.runs*1000;}
    public static int staticGraph(int add) {return ObjectState.root.next.box.owner.next.value(add);}
    public static int cycleIdentity(int value) {Node node=ObjectOps.node(value);return node.box.owner==node?node.value(2):0;}
    public static int readNode(Node node) {return node.box.value;}
    public static int constructorFailure(int divisor) {return new PartialBox(divisor).value;}
}
