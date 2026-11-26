import java.lang.reflect.Modifier;
import java.nio.file.*;
import java.util.*;
// Reads locked JDK field values in a disposable JVM oracle process.
public final class VersionPropsReference {
    public static void main(String[] args)throws Exception {
        Class<?> c=Class.forName("java.lang.VersionProps");var fields=c.getDeclaredFields();
        Arrays.sort(fields,Comparator.comparing(java.lang.reflect.Field::getName));
        var out=new StringBuilder("[");boolean first=true;
        for(var f:fields){if(!Modifier.isStatic(f.getModifiers()))continue;f.setAccessible(true);Object value=f.get(null);String descriptor,text;
            if(f.getType()==String.class){descriptor="Ljava/lang/String;";var hex=new StringBuilder("S:");if(value==null)hex.append("null");else for(char ch:((String)value).toCharArray())hex.append(String.format("%04x",(int)ch));text=hex.toString();}
            else if(f.getType()==boolean.class){descriptor="Z";text="Z:"+((boolean)value?1:0);}
            else if(f.getType()==int.class){descriptor="I";text="I:"+value;}
            else throw new AssertionError(f);
            if(!first)out.append(',');first=false;
            out.append("{\"name\":\"").append(f.getName()).append("\",\"descriptor\":\"").append(descriptor).append("\",\"value\":\"").append(text).append("\"}");
        }
        out.append(']');Files.writeString(Path.of(args[0]),out);
    }
}
