import dev.boom.signals.SignalNames;
import java.io.*;
import java.lang.reflect.*;
import java.nio.file.*;
public final class SignalNamesReference {
    public static void main(String[] args)throws Exception {
        if(args[0].equals("bad")){Class.forName(args[1]).getMethod("run").invoke(null);return;}
        Method find=Class.forName("jdk.internal.misc.Signal").getDeclaredMethod("findSignal0",String.class);find.setAccessible(true);
        try(var raw=new BufferedOutputStream(Files.newOutputStream(Path.of(args[0])))){
            for(int i=0;i<8*65536;i++)raw.write(((int)find.invoke(null,SignalNames.raw(i)))&255);
        }
        try(var out=new DataOutputStream(Files.newOutputStream(Path.of(args[1])))){
            for(int i=0;i<32;i++)try{out.writeInt((int)find.invoke(null,SignalNames.literal(i)));out.writeInt(0);}
            catch(InvocationTargetException e){if(!(e.getCause() instanceof NullPointerException)||!"name".equals(e.getCause().getMessage()))throw e;out.writeInt(0);out.writeInt(4);}
        }
        if(args.length>2){Class.forName(args[2]).getMethod("run").invoke(null);}
    }
}
