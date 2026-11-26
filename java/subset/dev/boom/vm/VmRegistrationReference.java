package dev.boom.vm;
import java.util.Scanner;
public final class VmRegistrationReference {
    public static void main(String[] args) throws Exception {
        if (args[0].equals("forged")) {
            Class.forName("dev.boom.vm.ForgedInitialize").getMethod("run").invoke(null);
            return;
        }
        Scanner input = new Scanner(System.in);
        while (input.hasNextLine()) {
            long offset = Long.parseUnsignedLong(input.nextLine().trim(), 16);
            System.out.printf("v %016x%n", VmRegistrationProgram.adjustment(offset));
        }
    }
}
