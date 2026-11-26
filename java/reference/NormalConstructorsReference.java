import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Constructor;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Arrays;
import java.io.File;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

/** Independent development oracle. Never linked into a guest image. */
public final class NormalConstructorsReference {
    static ClassLoader metadataLoader;
    static Class<?> type(String name) throws Exception {
        return switch (name) {
            case "Z" -> boolean.class; case "B" -> byte.class; case "C" -> char.class;
            case "S" -> short.class; case "I" -> int.class; case "J" -> long.class;
            case "F" -> float.class; case "D" -> double.class; case "V" -> void.class;
            default -> Class.forName(name.replace('/','.'),false,metadataLoader);
        };
    }
    static String name(Class<?> c) {
        if(c.isPrimitive()) return MethodType.methodType(c).toMethodDescriptorString().substring(2);
        return c.getName().replace('.','/');
    }
    static String bytes(byte[] value){return value==null?"-":HexFormat.of().formatHex(value);}
    public static void main(String[] args) throws Exception {
        String paths=System.getProperty("boom.oracle.classpath","");
        String[] entries=paths.isEmpty()?new String[0]:paths.split(java.util.regex.Pattern.quote(File.pathSeparator));
        URL[] urls=new URL[entries.length];for(int i=0;i<entries.length;i++)urls[i]=Path.of(entries[i]).toUri().toURL();
        // The signed original game's default package must not share the unsigned
        // oracle's defining loader. No original target initializer is executed.
        try(var loader=new URLClassLoader(urls,ClassLoader.getPlatformClassLoader())){
        metadataLoader=loader;
        var lookup=MethodHandles.privateLookupIn(Constructor.class,MethodHandles.lookup());
        VarHandle signature=lookup.findVarHandle(Constructor.class,"signature",String.class);
        VarHandle annotations=lookup.findVarHandle(Constructor.class,"annotations",byte[].class);
        VarHandle parameters=lookup.findVarHandle(Constructor.class,"parameterAnnotations",byte[].class);
        for(int i=0;i<args.length;i++){
            Class<?> c=type(args[i]);Constructor<?>[] all=c.getDeclaredConstructors();
            System.out.println("TYPE\t"+i+"\t"+args[i]+"\t"+all.length+"\t"+c.getConstructors().length);
            for(Constructor<?> ctor:all){
                String sig=(String)signature.get(ctor);
                System.out.println("CTOR\t"+i+"\t"+MethodType.methodType(void.class,ctor.getParameterTypes()).toMethodDescriptorString()+
                    "\t"+ctor.getModifiers()+"\t"+(sig==null?"-":Base64.getEncoder().encodeToString(sig.getBytes(StandardCharsets.UTF_8)))+
                    "\t"+bytes((byte[])annotations.get(ctor))+"\t"+bytes((byte[])parameters.get(ctor))+"\t"+
                    String.join(",",Arrays.stream(ctor.getExceptionTypes()).map(NormalConstructorsReference::name).toList()));
            }
        }
        }
    }
}
