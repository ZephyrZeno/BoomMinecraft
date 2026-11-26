import java.io.*;
import java.lang.reflect.Method;
import java.nio.file.*;
// Runs only inside a disposable JVM reference process; saves no game data.
public final class SystemStreamsReference {
    public static void main(String[] args)throws Exception {
        if(args[0].equals("bad")){Class.forName(args[1]).getMethod("run").invoke(null);return;}
        InputStream oldIn=System.in;PrintStream oldOut=System.out,oldErr=System.err;
        Method[] set=new Method[3];String[] names={"setIn0","setOut0","setErr0"};
        for(int i=0;i<3;i++){set[i]=System.class.getDeclaredMethod(names[i],i==0?InputStream.class:PrintStream.class);set[i].setAccessible(true);}
        var a=new ByteArrayInputStream(new byte[]{1,2});var b=new ByteArrayInputStream(new byte[]{3,4});
        var x=new PrintStream(new ByteArrayOutputStream());var y=new PrintStream(new ByteArrayOutputStream());
        Object[] objects={null,a,b,x,y};
        try(var out=new DataOutputStream(Files.newOutputStream(Path.of(args[0])))) {
            try {
                for(Method m:set)m.invoke(null,new Object[]{null});
                for(int i=0;i<1024;i++) {
                    int op=i%3,choice=i%5==0?0:op==0?1+(i&1):3+(i&1);
                    set[op].invoke(null,new Object[]{objects[choice]});
                    int mask=0;Object[] fields={System.in,System.out,System.err};
                    for(int j=0;j<3;j++){int id=0;while(id<5&&objects[id]!=fields[j])id++;if(id==5)throw new AssertionError("Unknown stream");mask|=id<<(j*3);}
                    out.writeInt(mask);
                }
            } finally {set[0].invoke(null,oldIn);set[1].invoke(null,oldOut);set[2].invoke(null,oldErr);x.close();y.close();}
        }
    }
}
