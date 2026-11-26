import java.io.*;
import dev.boom.fields.FieldProgram;
public final class FieldReference {
    public static void main(String[] args)throws Exception {
        try(BufferedReader r=new BufferedReader(new InputStreamReader(System.in))){
            String line;while((line=r.readLine())!=null){String[] p=line.split(" ");System.out.println(Long.toUnsignedString(FieldProgram.run(Integer.parseInt(p[0]),Integer.parseInt(p[1])),16));}
        }
    }
}
