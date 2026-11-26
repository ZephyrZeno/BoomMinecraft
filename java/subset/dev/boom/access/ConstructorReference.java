package dev.boom.access;
import dev.boom.access.child.ConstructorProgram;
import java.util.Scanner;
public final class ConstructorReference {
    public static void main(String[] args) {
        Scanner in = new Scanner(System.in);
        while (in.hasNextLine()) {
            int value = (int) Long.parseUnsignedLong(in.nextLine().trim(), 16);
            long result;
            switch (args[0]) {
                case "wide": result = ConstructorProgram.wide(value); break;
                case "child": result = Integer.toUnsignedLong(ConstructorProgram.child(value)); break;
                case "anonymous": result = Integer.toUnsignedLong(ConstructorProgram.anonymous(value)); break;
                case "chained": result = Integer.toUnsignedLong(ConstructorProgram.chained(value)); break;
                default: result = Integer.toUnsignedLong(ConstructorProgram.enumValues(value)); break;
            }
            System.out.printf("v %016x%n", result);
        }
    }
}
