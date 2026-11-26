package dev.boom.prefix;
import java.io.BufferedReader;
import java.io.InputStreamReader;
public final class PrefixReference {
    public static void main(String[] args)throws Exception {
        try(var in=new BufferedReader(new InputStreamReader(System.in))){String line;
            while((line=in.readLine())!=null){if(line.isEmpty())continue;String[] a=line.split(" ");
                int x=(int)Long.parseUnsignedLong(a[0],16),y=a.length>1?(int)Long.parseUnsignedLong(a[1],16):0,z=a.length>2?(int)Long.parseUnsignedLong(a[2],16):0;
                int v=switch(args[0]){case "offset"->PrefixProgram.offset(x,y,z);case "start"->PrefixProgram.start(x,y);case "end"->PrefixProgram.end(x,y);
                    case "raw"->PrefixProgram.raw(x,y,z);case "dynamic"->PrefixProgram.dynamic(x);case "nullOrder"->PrefixProgram.nullOrder(x);
                    case "fullHeap"->PrefixProgram.fullHeap(x);case "parallel"->PrefixProgram.parallel(x);default->throw new AssertionError(args[0]);};
                System.out.printf("v %016x%n",Integer.toUnsignedLong(v));
            }
        }
    }
}
