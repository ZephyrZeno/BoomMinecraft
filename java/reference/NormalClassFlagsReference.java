import java.io.File;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import jdk.internal.reflect.Reflection;
public final class NormalClassFlagsReference {
    static Class<?> type(String name,ClassLoader loader) throws Exception {
        return switch(name){
            case "Z"->boolean.class;case "B"->byte.class;case "C"->char.class;case "S"->short.class;
            case "I"->int.class;case "J"->long.class;case "F"->float.class;case "D"->double.class;case "V"->void.class;
            default->Class.forName(name.replace('/','.'),false,loader);
        };
    }
    public static void main(String[] args) throws Exception {
        String paths=System.getProperty("boom.oracle.classpath","");String[] entries=paths.isEmpty()?new String[0]:paths.split(java.util.regex.Pattern.quote(File.pathSeparator));
        URL[] urls=new URL[entries.length];for(int i=0;i<entries.length;i++)urls[i]=Path.of(entries[i]).toUri().toURL();
        try(var loader=new URLClassLoader(urls,ClassLoader.getPlatformClassLoader())){
            for(String name:args){Class<?> c=type(name,loader);System.out.println(name+"\t"+Reflection.getClassAccessFlags(c)+"\t"+c.getModifiers());}
        }
    }
}
