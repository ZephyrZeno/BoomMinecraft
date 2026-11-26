package dev.boom.subset;

/** Compiler fixtures, never a substitute for a Minecraft client. */
public final class ObjectKernels {
    private int a;
    private long b;
    private float f;
    private double d;
    private byte tiny;
    private char letter;
    private short small;
    private boolean flag;
    private ObjectKernels next;
    private int[] values;
    private final int bias;

    private ObjectKernels() { bias=7; }
    private ObjectKernels(int seed) { this(); a=seed; b=seed; }
    private ObjectKernels(long seed) { this(); b=seed; }
    private void add(int delta) { a+=delta; }
    private int read() { return a+bias; }
    private int postInt() { return a++; }
    private long postLong() { return b++; }
    private int constant() { return 17; }
    private static ObjectKernels make(int seed) { return new ObjectKernels(seed); }
    private static ObjectKernels choose(int selector) { return selector==0?null:make(selector); }

    public static int intObject(int seed,int delta) {
        ObjectKernels value=make(seed); value.add(delta);
        int before=value.postInt(); return before^value.read();
    }
    public static long longObject(long seed,int count) {
        ObjectKernels value=new ObjectKernels(seed); long sum=0;
        for(int i=0;i<count;i++) sum+=value.postLong();
        return sum^value.b;
    }
    public static float floatObject(float seed,float delta) {
        ObjectKernels value=new ObjectKernels(); value.f=seed; value.f+=delta; return -value.f;
    }
    public static double doubleObject(double seed,double delta) {
        ObjectKernels value=new ObjectKernels(); value.d=seed; value.d*=delta; return value.d;
    }
    public static int narrowFields(int seed) {
        ObjectKernels value=new ObjectKernels();
        value.tiny=(byte)seed; value.letter=(char)seed; value.small=(short)seed; value.flag=(seed&1)!=0;
        return value.tiny+(value.letter<<8)+(value.small<<16)+(value.flag?13:0);
    }
    public static int linkedObjects(int count,int seed) {
        ObjectKernels head=null;
        for(int i=0;i<count;i++) { ObjectKernels value=new ObjectKernels(seed+i); value.next=head; head=value; }
        int sum=0; while(head!=null) { sum+=head.read(); head=head.next; }
        return sum;
    }
    public static int arrayObject(int count,int seed) {
        ObjectKernels value=new ObjectKernels(seed); value.values=new int[count];
        for(int i=0;i<count;i++) value.values[i]=seed+i;
        int sum=value.read(); for(int i=0;i<count;i++) sum+=value.values[i];
        return sum;
    }
    public static int cycleObject(int seed) {
        ObjectKernels first=make(seed),second=make(seed+1); first.next=second; second.next=first;
        return first.next.next.read()^second.read();
    }
    public static int nullField(int selector) { return choose(selector).a; }
    public static int nullWrite(int selector,int value) { ObjectKernels obj=choose(selector); obj.a=value; return obj.a; }
    public static int nullCall(int selector) { return choose(selector).constant(); }
    public static int identity(int seed) { ObjectKernels first=make(seed),second=make(seed); return first==second?1:(first==first?2:3); }
    public static int defaults(int selector) { ObjectKernels obj=new ObjectKernels(); return (obj.next==null&&obj.values==null&&!obj.flag&&obj.a==0&&obj.b==0&&obj.f==0&&obj.d==0)?selector:19; }
    public static int constructorFailure(int seed) { return make(seed).a/seed; }

    // A rooted cycle with a primitive array exercises generated reference-field layout.
    public static ObjectKernels retainedGraph(int count) {
        ObjectKernels first=make(11),second=make(23); first.next=second; second.next=first;
        second.values=new int[count]; return first;
    }
}
