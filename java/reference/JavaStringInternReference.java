import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

// Offline JVM oracle only. Inputs arrive as raw UTF16, not Java constants.
public class JavaStringInternReference {
    static int le32(DataInputStream in) throws IOException {return Integer.reverseBytes(in.readInt());}
    public static void main(String[] args) throws Exception {
        var lines=new ArrayList<String>();var live=new ArrayList<String>();
        try(var in=new DataInputStream(Files.newInputStream(Path.of(args[0])))){
            if(le32(in)!=0x4a494e44)throw new IOException("Bad intern fixture");
            int count=le32(in);
            for(int id=0;id<count;id++){
                char[] units=new char[le32(in)];for(int i=0;i<units.length;i++)units[i]=(char)Short.toUnsignedInt(Short.reverseBytes(in.readShort()));
                String first=new String(units),canonical=first.intern(),second=new String(units);
                lines.add(id+"\t"+Integer.toUnsignedString(first.hashCode())+"\t"+(canonical==first?1:0)+"\t"+(second.intern()==canonical?1:0));
                live.add(canonical);
            }
            if(in.read()!=-1)throw new IOException("Trailing intern fixture data");
        }
        Files.write(Path.of(args[1]),lines,StandardCharsets.UTF_8);
        if(live.size()!=lines.size())throw new AssertionError();
    }
}
