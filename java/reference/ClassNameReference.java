import java.io.BufferedReader;
import java.io.InputStreamReader;
import dev.boom.lookup.Counters;
public final class ClassNameReference {
    private static String value(String s){if(s.equals("null"))return null;if(s.equals("-"))return "";String[] w=s.split(",");char[] c=new char[w.length];for(int i=0;i<c.length;i++)c[i]=(char)Integer.parseInt(w[i],16);return new String(c);}
    private static String text(String s){if(s==null)return "null";if(s.isEmpty())return "-";StringBuilder b=new StringBuilder();for(int i=0;i<s.length();i++)b.append(String.format("%04x",(int)s.charAt(i)));return b.toString();}
    public static void main(String[] args)throws Exception {
        var r=new BufferedReader(new InputStreamReader(System.in));String line;
        while((line=r.readLine())!=null){String[] f=line.split(" ");String name=value(f[2]);
            try{Class<?> c=Class.forName(name,f[1].equals("1"),f[0].equals("0")?null:ClassNameReference.class.getClassLoader());
                ClassLoader loader=c.getClassLoader();String kind=loader==null?"bootstrap":loader==ClassLoader.getPlatformClassLoader()?"platform":"application";
                System.out.println("v "+text(c.getName())+" "+kind+" "+Counters.mask);
            }catch(Throwable e){String message=e instanceof ClassNotFoundException?text(e.getMessage()):"-";System.out.println("e "+e.getClass().getName()+" "+(e.getCause()==null?"-":e.getCause().getClass().getName())+" "+message+" "+Counters.mask);}
        }
    }
}
