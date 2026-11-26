import java.io.BufferedReader;
import java.io.InputStreamReader;
import dev.boom.split.SplitProgram;
public final class SplitReference {
    private static String value(String s) {
        if (s.equals("null")) return null;
        if (s.equals("-")) return new String(new char[0]);
        String[] words = s.split(","); char[] chars = new char[words.length];
        for (int i=0;i<chars.length;i++) chars[i]=(char)Integer.parseInt(words[i],16);
        return new String(chars);
    }
    private static String text(String s) {
        if (s.isEmpty()) return "-";
        StringBuilder b=new StringBuilder();
        for (int i=0;i<s.length();i++) b.append(String.format("%04x",(int)s.charAt(i)));
        return b.toString();
    }
    public static void main(String[] args) throws Exception {
        BufferedReader r=new BufferedReader(new InputStreamReader(System.in));String line;
        while ((line=r.readLine())!=null) {
            String[] f=line.split(" ");String source=value(f[2]),regex=value(f[3]);
            try {
                String[] a=SplitProgram.split(source,regex,Integer.parseInt(f[1]),Integer.parseInt(f[0]));
                StringBuilder b=new StringBuilder("v ").append(a.length);
                for(String s:a)b.append(' ').append(text(s)).append('@').append(s==source?'1':'0');
                System.out.println(b);
            } catch (Throwable e) {System.out.println("e "+e.getClass().getName());}
        }
    }
}
