import java.io.*;
import java.lang.reflect.Method;
import java.nio.file.*;

// Isolated JVM oracle; no game directories or account data are accessed.
public final class SourceStreamsReference {
    public static void main(String[] args)throws Exception{
        Method[] set=new Method[3];String[] names={"setIn0","setOut0","setErr0"};
        for(int i=0;i<3;i++){set[i]=System.class.getDeclaredMethod(names[i],i==0?InputStream.class:PrintStream.class);set[i].setAccessible(true);}
        InputStream oldIn=System.in;PrintStream oldOut=System.out,oldErr=System.err;
        var input=new ByteArrayInputStream(new byte[]{7,10,(byte)255});var out=new PrintStream(new ByteArrayOutputStream());var err=new PrintStream(new ByteArrayOutputStream());
        String reads;
        try{
            set[0].invoke(null,input);set[1].invoke(null,out);set[2].invoke(null,err);
            if(System.in!=input||System.out!=out||System.err!=err)throw new AssertionError("Stream identity changed");
            reads=input.available()+","+input.read()+","+input.read()+","+input.read()+","+input.read();
            input.reset();reads+=","+input.available();
            for(Method m:set)m.invoke(null,new Object[]{null});
            if(System.in!=null||System.out!=null||System.err!=null)throw new AssertionError("Null stream rejected");
        }finally{set[0].invoke(null,oldIn);set[1].invoke(null,oldOut);set[2].invoke(null,oldErr);out.close();err.close();}
        Files.writeString(Path.of(args[0]),reads+"\n");
    }
}
