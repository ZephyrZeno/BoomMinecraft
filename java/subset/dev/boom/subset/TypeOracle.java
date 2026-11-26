package dev.boom.subset;
import java.io.BufferedReader;
import java.io.InputStreamReader;

/** Input preparation/reference test only. Never initializes a Minecraft class. */
public final class TypeOracle {
    static Class<?> type(String name) throws Exception {
        return switch(name) {
            case "boolean" -> boolean.class;
            case "byte" -> byte.class;
            case "char" -> char.class;
            case "short" -> short.class;
            case "int" -> int.class;
            case "long" -> long.class;
            case "float" -> float.class;
            case "double" -> double.class;
            default -> Class.forName(name, false, TypeOracle.class.getClassLoader());
        };
    }
    public static void main(String[] args) throws Exception {
        var reader=new BufferedReader(new InputStreamReader(System.in));String line;
        while((line=reader.readLine())!=null) {
            var pair=line.split(" ");
            System.out.println(type(pair[1]).isAssignableFrom(type(pair[0]))?"1":"0");
        }
    }
}
