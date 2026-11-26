import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.Locale;

// JVM reference only. Native execution uses VM Locale storage fixtures.
public final class LowercaseReference {
    public static void main(String[] args) throws Exception {
        var reader=new BufferedReader(new InputStreamReader(System.in));String line;
        while((line=reader.readLine())!=null) {
            String[] fields=line.split(" ");String input=null;
            if(!fields[1].equals("null")) {
                String[] words=fields[1].equals("-")?new String[0]:fields[1].split(",");
                char[] chars=new char[words.length];for(int i=0;i<chars.length;i++)chars[i]=(char)Integer.parseUnsignedInt(words[i],16);
                input=new String(chars);
            }
            Locale locale=fields[0].equals("null")?null:fields[0].equals("-")?Locale.ROOT:Locale.forLanguageTag(fields[0]);
            try {
                String lower=input.toLowerCase(locale);var result=new StringBuilder("v ").append(lower==input?1:0).append(' ');
                for(int i=0;i<lower.length();i++)result.append(String.format("%04x",(int)lower.charAt(i)));
                System.out.println(result);
            }catch(Throwable failure){System.out.println("e "+failure.getClass().getName());}
        }
    }
}
