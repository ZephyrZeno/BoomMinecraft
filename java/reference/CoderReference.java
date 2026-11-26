import java.io.*;
import java.lang.reflect.*;
public final class CoderReference {
 public static void main(String[] args)throws Exception {Method mix=Class.forName("java.lang.StringConcatHelper").getDeclaredMethod("mix",long.class,String.class);mix.setAccessible(true);try(var input=new BufferedReader(new InputStreamReader(System.in))){String line;while((line=input.readLine())!=null){String[] p=line.split(" ",-1);String value=null;if(!p[1].equals("null")){String[] units=p[1].isEmpty()?new String[0]:p[1].split(":");char[] data=new char[units.length];for(int i=0;i<data.length;i++)data[i]=(char)Integer.parseInt(units[i],16);value=new String(data);}try{long result=(Long)mix.invoke(null,Long.parseUnsignedLong(p[0],16),value);System.out.printf("v %016x%n",result);}catch(InvocationTargetException e){System.out.println("e "+e.getCause().getClass().getName());}}}}
}
