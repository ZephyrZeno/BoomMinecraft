package dev.boom.chars;
import java.io.BufferedReader;
import java.io.InputStreamReader;
public final class CharsReference {
    public static void main(String[] args) throws Exception {
        try(var input=new BufferedReader(new InputStreamReader(System.in))) {
            String line;while((line=input.readLine())!=null){if(line.isEmpty())continue;
                String[] a=line.split(" ");int n=(int)Long.parseUnsignedLong(a[0],16);
                if(args[0].equals("pair")) {
                    char[] r=CharsProgram.pair(n,(int)Long.parseUnsignedLong(a[1],16));
                    var text=new StringBuilder();for(char c:r)text.append(String.format("%04x",(int)c));
                    System.out.println(text);continue;
                }
                int r=switch(args[0]) {
                    case "relation" -> CharsProgram.relation(n,(int)Long.parseUnsignedLong(a[1],16));
                    case "twice" -> CharsProgram.twice(n); case "dynamic" -> CharsProgram.dynamic(n);
                    case "bounds" -> CharsProgram.bounds(n); case "nullReceiver" -> CharsProgram.nullReceiver(n);
                    case "fullHeap" -> CharsProgram.fullHeap(n); case "copyTypes" -> CharsProgram.copyTypes(n);
                    case "parallel" -> CharsProgram.parallel(n);default -> throw new AssertionError(args[0]);
                };
                System.out.printf("v %016x%n",Integer.toUnsignedLong(r));
            }
        }
    }
}
