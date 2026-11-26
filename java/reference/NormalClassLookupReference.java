import java.nio.file.*;
import java.nio.charset.StandardCharsets;
public final class NormalClassLookupReference {
    public static void main(String[] args)throws Exception {
        int count=0;for(String name:Files.readAllLines(Path.of(args[0]),StandardCharsets.UTF_8)) {
            try {Class<?> c=Class.forName(name,false,null);System.out.println(name+"\tOK\t"+c.getName());}
            catch(ClassNotFoundException e){System.out.println(name+"\tCNFE");}count++;
        }
        try{Class.forName(null,false,null);throw new AssertionError();}catch(NullPointerException expected){}
        System.err.println("name_cases\t"+count);
        for(String name:new String[]{"java.lang.Thread$State"}){
            for(Object o:Class.forName(name,true,null).getEnumConstants()){Enum<?> e=(Enum<?>)o;System.err.println("enum\t"+name+"\t"+e.name()+"\t"+e.ordinal());}
        }
    }
}
