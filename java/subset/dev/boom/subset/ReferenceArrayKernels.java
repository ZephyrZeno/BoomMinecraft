package dev.boom.subset;
public final class ReferenceArrayKernels {
    private int value;
    private ReferenceArrayKernels[] links;
    private ReferenceArrayKernels(int value) { this.value=value; }
    private static ReferenceArrayKernels[] create(int count,int seed) {
        ReferenceArrayKernels[] array=new ReferenceArrayKernels[count];
        for(int i=0;i<count;i++) array[i]=new ReferenceArrayKernels(seed+i);
        return array;
    }
    private static int sum(ReferenceArrayKernels[] array) {
        int sum=0; for(int i=0;i<array.length;i++) if(array[i]!=null) sum+=array[i].value;
        return sum;
    }
    public static int sumArray(int count,int seed) { return sum(create(count,seed)); }
    public static int nullElements(int count,int index) {
        ReferenceArrayKernels[] array=new ReferenceArrayKernels[count];
        if(count>0) array[0]=new ReferenceArrayKernels(31);
        return array[index]==null?7:array[index].value;
    }
    public static int replaceArray(int count,int seed) {
        ReferenceArrayKernels[] array=create(count,seed); array[0]=null; return sum(array);
    }
    public static int arrayField(int count,int seed) {
        ReferenceArrayKernels obj=new ReferenceArrayKernels(seed); obj.links=create(count,seed); return sum(obj.links);
    }
    public static int cyclicArray(int seed) {
        ReferenceArrayKernels obj=new ReferenceArrayKernels(seed); obj.links=new ReferenceArrayKernels[2];
        obj.links[0]=obj;obj.links[1]=obj;return obj.links[0].links[1].value;
    }
    public static int nullArray(int selector) {
        ReferenceArrayKernels[] array=selector==0?null:new ReferenceArrayKernels[selector];return array.length;
    }
    public static int identity(int count) { ReferenceArrayKernels[] a=new ReferenceArrayKernels[count],b=new ReferenceArrayKernels[count];return a==b?1:(a==a?2:3); }
    public static ReferenceArrayKernels[] retainedArray(int count) {
        ReferenceArrayKernels[] array=create(count,71);
        for(int i=0;i<count;i++) array[i].links=array;return array;
    }
}
