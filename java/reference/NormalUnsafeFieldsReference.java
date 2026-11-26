import java.nio.file.*;
import java.lang.reflect.*;
import jdk.internal.misc.Unsafe;

// Development oracle: check declarations/relations, never compare VM-specific
// numeric offsets with Boom's opaque cookies and never initialize target types.
public final class NormalUnsafeFieldsReference {
    static String text(String hex) {
        byte[] b=java.util.HexFormat.of().parseHex(hex);char[] c=new char[b.length/2];
        for(int i=0;i<c.length;i++)c[i]=(char)((b[2*i]&255)|((b[2*i+1]&255)<<8));
        return new String(c);
    }
    static int kind(Class<?> c) {
        if(!c.isPrimitive())return 9;
        return switch(c.getName()){case "boolean"->1;case "byte"->2;case "char"->3;case "short"->4;case "int"->5;case "long"->6;case "float"->7;case "double"->8;default->throw new AssertionError();};
    }
    public static void main(String[] args)throws Exception {
        Unsafe u=Unsafe.getUnsafe();int count=0;
        for(String line:Files.readAllLines(Path.of(args[0]))) {
            String[] p=line.split("\t");Class<?> c=Class.forName(p[7].replace('/','.'),false,null);String name=text(p[6]);
            Field f=c.getDeclaredField(name);long a=u.objectFieldOffset(c,name),b=u.objectFieldOffset(c,new String(name));
            if(a!=b||kind(f.getType())!=Integer.parseInt(p[3])||Modifier.isStatic(f.getModifiers())!=((Integer.parseInt(p[2])&8)!=0))throw new AssertionError("Lookup/source relation changed: "+line);
            count++;
        }
        int errors=0;
        try{u.objectFieldOffset(String.class,"__boom_missing_field__");throw new AssertionError();}catch(InternalError expected){errors++;}
        try{u.objectFieldOffset(null,"value");throw new AssertionError();}catch(NullPointerException expected){errors++;}
        try{u.objectFieldOffset(String.class,null);throw new AssertionError();}catch(NullPointerException expected){errors++;}
        System.out.println("cases\t"+count);System.out.println("errors\t"+errors);
    }
}
