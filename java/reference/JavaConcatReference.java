import java.io.*;
import java.lang.invoke.*;
import java.nio.file.*;
import java.util.*;

/** Development oracle only. The game executes the generated assembly. */
public final class JavaConcatReference {
    static int integer(DataInputStream in) throws IOException { return Integer.reverseBytes(in.readInt()); }
    static long wide(DataInputStream in) throws IOException { return Long.reverseBytes(in.readLong()); }
    static String text(DataInputStream in, int length) throws IOException {
        if (length < 0) return null;
        char[] chars = new char[length];
        for (int i=0;i<length;i++) chars[i]=Character.reverseBytes(in.readChar());
        return new String(chars);
    }
    static void integer(DataOutputStream out,int value) throws IOException { out.writeInt(Integer.reverseBytes(value)); }
    public static void main(String[] args) throws Throwable {
        try (var in=new DataInputStream(Files.newInputStream(Path.of(args[0])));
             var out=new DataOutputStream(Files.newOutputStream(Path.of(args[1])))) {
            if(integer(in)!=0x4a434f4e) throw new IOException("Bad concat cases");
            int count=integer(in);integer(out,0x4a434f55);integer(out,count);
            for(int c=0;c<count;c++) {
                int n=integer(in);Object[] values=new Object[n];Class<?>[] types=new Class<?>[n];int[] kinds=new int[n];
                for(int i=0;i<n;i++) {
                    int k=integer(in);kinds[i]=k;long bits=wide(in);String text=text(in,integer(in));
                    switch(k) {
                        case 1 -> { types[i]=int.class;values[i]=(int)bits; }
                        case 2 -> { types[i]=long.class;values[i]=bits; }
                        case 3 -> { types[i]=boolean.class;values[i]=bits!=0; }
                        case 4 -> { types[i]=char.class;values[i]=(char)bits; }
                        case 5 -> { types[i]=String.class;values[i]=text; }
                        default -> throw new IOException("Unknown concat argument");
                    }
                }
                int parts=integer(in),dynamic=0;StringBuilder recipe=new StringBuilder();List<String> constants=new ArrayList<>();
                for(int i=0;i<parts;i++) {
                    int k=integer(in),index=integer(in);String text=text(in,integer(in));
                    if(k==0) { recipe.append('\2');constants.add(text); }
                    else { if(index!=dynamic || k!=kinds[dynamic++])throw new IOException("Case argument order differs");recipe.append('\1'); }
                }
                if(dynamic!=n)throw new IOException("Case arity differs");
                var target=StringConcatFactory.makeConcatWithConstants(MethodHandles.lookup(),"concat",MethodType.methodType(String.class,types),recipe.toString(),constants.toArray()).getTarget();
                String value=(String)target.invokeWithArguments(values);integer(out,value.length());
                for(int i=0;i<value.length();i++)out.writeChar(Character.reverseBytes(value.charAt(i)));
            }
            if(in.read()!=-1)throw new IOException("Trailing concat cases");
            System.out.println("JVM concat cases="+count);
        }
    }
}
