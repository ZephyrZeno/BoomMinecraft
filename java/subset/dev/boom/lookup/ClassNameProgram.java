package dev.boom.lookup;
public final class ClassNameProgram {
    public static Class<?> mirror(int which) {
        return switch(which){case 0->Aa.class;case 1->BB.class;case 2->Child.class;
            case 3->Passive.class;case 4->ArrayTarget[].class;case 5->int[][].class;
            case 6->String.class;case 7->Class.class;case 8->BadInit.class;
            case 9->ArrayTarget.class;case 10->Parent.class;default->null;};
    }
    public static Class<?> lookup(String name,boolean initialize,ClassLoader loader,int operation) throws ClassNotFoundException {
        if(operation>=0)return mirror(operation);
        return Class.forName(name,initialize,loader);
    }
}
