package dev.boom.subset;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Method;
import java.util.Arrays;

/** JVM reference only; generated assembly is executed in a separate native process. */
public final class IntOracle {
    public static void main(String[] args) throws Exception {
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = reader.readLine()) != null) {
            String[] parts = line.split(" ");
            Class<?>[] types = new Class<?>[parts.length - 1];
            Arrays.fill(types, int.class);
            Object[] values = new Object[types.length];
            for (int i = 0; i < values.length; i++) values[i] = Integer.valueOf(parts[i + 1]);
            Method method = IntKernels.class.getMethod(parts[0], types);
            System.out.println(method.invoke(null, values));
        }
    }
}
