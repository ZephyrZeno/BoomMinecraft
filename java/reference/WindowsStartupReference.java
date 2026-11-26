import java.io.DataOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
/** Isolated JVM oracle for the original Windows native method; never game code. */
public final class WindowsStartupReference {
    public static void main(String[] args) throws Exception {
        var method=Class.forName("sun.io.Win32ErrorMode").getDeclaredMethod("setErrorMode",long.class);
        method.setAccessible(true);
        long saved=(Long)method.invoke(null,1L);
        try(var out=new DataOutputStream(Files.newOutputStream(Path.of(args[0])))) {
            long[] modes={0,1,2,3,0x8000,0x8001,0x8002,0x8003};
            for(int i=0;i<256;i++) {
                long mode=((0xa95a00feL+i)<<32)|modes[i%modes.length];
                out.writeLong(mode);out.writeLong((Long)method.invoke(null,mode));
            }
        } finally { method.invoke(null,saved); }
    }
}
