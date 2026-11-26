package dev.boom.replace;
import java.io.BufferedReader;
import java.io.InputStreamReader;
public final class ReplaceReference {
    public static void main(String[] args)throws Exception {
        try(var input=new BufferedReader(new InputStreamReader(System.in))) {
            String line;while((line=input.readLine())!=null){if(line.isEmpty())continue;
                String[] a=line.split(" ");int n=(int)Long.parseUnsignedLong(a[0],16);
                if(args[0].equals("pair")) {
                    String r=ReplaceProgram.pair(n,(int)Long.parseUnsignedLong(a[1],16));
                    var text=new StringBuilder();for(int i=0;i<r.length();i++)text.append(String.format("%04x",(int)r.charAt(i)));
                    System.out.println(text);continue;
                }
                int old=a.length>1?(int)Long.parseUnsignedLong(a[1],16):0,neo=a.length>2?(int)Long.parseUnsignedLong(a[2],16):0;
                int result=switch(args[0]) {
                    case "relation"->ReplaceProgram.relation(n,old,neo);case "twice"->ReplaceProgram.twice(n,old,neo);
                    case "dynamic"->ReplaceProgram.dynamic(n);case "allocation"->ReplaceProgram.allocation(n);
                    case "fullHeap"->ReplaceProgram.fullHeap(n);case "nullReceiver"->ReplaceProgram.nullReceiver(n);
                    case "parallel"->ReplaceProgram.parallel(n);default->throw new AssertionError(args[0]);
                };
                System.out.printf("v %016x%n",Integer.toUnsignedLong(result));
            }
        }
    }
}
