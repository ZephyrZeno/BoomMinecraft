package dev.boom.reflection;
import java.io.BufferedReader;
import java.io.InputStreamReader;
public final class ClassQueryReference {
    public static void main(String[] args) throws Exception {
        try(var input=new BufferedReader(new InputStreamReader(System.in))) {
            String line;while((line=input.readLine())!=null){if(line.isEmpty())continue;
                int n=(int)Long.parseUnsignedLong(line,16);
                int result=switch(args[0]) {
                    case "hidden"->ClassQueryProgram.hidden(n);
                    case "component"->ClassQueryProgram.component(n);
                    case "depth"->ClassQueryProgram.depth(n);
                    case "untouched"->ClassQueryProgram.untouched(n);
                    case "nullHidden"->ClassQueryProgram.nullHidden(n);
                    case "nullComponent"->ClassQueryProgram.nullComponent(n);
                    default->throw new AssertionError(args[0]);
                };
                System.out.printf("v %016x%n",Integer.toUnsignedLong(result));
            }
        }
    }
}
