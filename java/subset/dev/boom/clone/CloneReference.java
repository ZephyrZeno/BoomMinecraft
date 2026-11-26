package dev.boom.clone;
import java.util.Scanner;
public final class CloneReference {
    public static void main(String[] args) {
        Scanner in = new Scanner(System.in);
        while (in.hasNextLine()) {
            int v = (int) Long.parseUnsignedLong(in.nextLine().trim(), 16);
            long result;
            switch (args[0]) {
                case "checksum": result = CloneProgram.checksum(v); break;
                case "relations": result = Integer.toUnsignedLong(CloneProgram.relations(v)); break;
                case "nullReceiver": result = Integer.toUnsignedLong(CloneProgram.nullReceiver(v)); break;
                case "fullHeap": result = Integer.toUnsignedLong(CloneProgram.fullHeap(v)); break;
                default: result = Integer.toUnsignedLong(CloneProgram.parallel(v)); break;
            }
            System.out.printf("v %016x%n", result);
        }
    }
}
