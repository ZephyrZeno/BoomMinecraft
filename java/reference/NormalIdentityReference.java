public class NormalIdentityReference {
    static final class Overridden { public int hashCode(){return 731;} }
    public static void main(String[] args) {
        Object a=new Object(); Object[] refs=new Object[]{a}; int[] ints={1,2,3};
        for(Object value:new Object[]{a,refs,ints}) {
            int h=System.identityHashCode(value);
            for(int i=0;i<4096;i++)if(value.hashCode()!=h || System.identityHashCode(value)!=h)throw new AssertionError("identity changed");
        }
        int before=System.identityHashCode(ints);ints[0]=12345;
        if(System.identityHashCode(ints)!=before || System.identityHashCode(null)!=0)throw new AssertionError("null/mutation differs");
        Overridden overridden=new Overridden();
        if(overridden.hashCode()!=731 || System.identityHashCode(overridden)!=System.identityHashCode(overridden))throw new AssertionError("override affected identity");
        System.out.println("identity_relations=true null=0 mutation_preserved=true override_preserved=true");
    }
}
