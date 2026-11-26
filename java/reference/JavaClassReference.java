import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

// JVM development oracle only. Never linked into the delivered runtime.
public class JavaClassReference {
    public static void main(String[] args) throws Exception {
        Class<?>[] values={boolean.class,byte.class,char.class,short.class,int.class,long.class,float.class,double.class,void.class,
            Object.class,String.class,Class.class,Number.class,Integer.class,Runnable.class,Cloneable.class,
            java.io.Serializable.class,Module.class,ClassLoader.class,java.sql.Connection.class,
            int[].class,int[][].class,Object[].class,String[].class,Object[][].class,Class[][].class};
        var lines=new ArrayList<String>();
        for(Class<?> target:values) for(Class<?> source:values)
            lines.add(target.getName()+"\t"+source.getName()+"\t"+(target.isAssignableFrom(source)?1:0));
        Files.write(Path.of(args[0]),lines,StandardCharsets.UTF_8);
    }
}
