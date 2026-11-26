package dev.boom.arrays;
import java.util.Scanner;
public final class MultiArrayReference {
    public static void main(String[] args) throws Exception {
        if(args[0].equals("bad")) { Class.forName(args[1]).getMethod("run").invoke(null); return; }
        Scanner input=new Scanner(System.in);
        while(input.hasNextLine()) {
            String[] fields=input.nextLine().trim().split(" +");
            int value=(int)Long.parseUnsignedLong(fields[0],16);
            long result;
            switch(args[0]) {
                case "primitives": result=MultiArrayProgram.primitives(value,(int)Long.parseUnsignedLong(fields[1],16));break;
                case "jagged": result=Integer.toUnsignedLong(MultiArrayProgram.jagged(value));break;
                case "references": result=Integer.toUnsignedLong(MultiArrayProgram.references(value));break;
                case "partial": result=Integer.toUnsignedLong(MultiArrayProgram.partial(value));break;
                case "negative": result=Integer.toUnsignedLong(MultiArrayProgram.negative(value));break;
                case "nullAndBounds": result=Integer.toUnsignedLong(MultiArrayProgram.nullAndBounds(value));break;
                case "fullHeap": result=Integer.toUnsignedLong(MultiArrayProgram.fullHeap(value));break;
                default: result=Integer.toUnsignedLong(MultiArrayProgram.parallel(value));break;
            }
            System.out.printf("v %016x%n",result);
        }
    }
}
