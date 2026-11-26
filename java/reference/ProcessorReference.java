import java.io.BufferedReader;
import java.io.InputStreamReader;
import dev.boom.processors.ProcessorProgram;
public final class ProcessorReference {
    public static void main(String[] args)throws Exception {
        System.out.println("READY");
        var reader=new BufferedReader(new InputStreamReader(System.in));String line;
        while((line=reader.readLine())!=null)System.out.println(ProcessorProgram.count(Integer.parseInt(line)));
    }
}
