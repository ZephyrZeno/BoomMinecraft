package dev.boom.subset;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.InvocationTargetException;

/** Reference-only invocation of exact locked class/method/descriptor triples. */
public final class ClassNumericOracle {
    public static void main(String[] args) throws Exception {
        var reader=new BufferedReader(new InputStreamReader(System.in));String line;
        while((line=reader.readLine())!=null) {
            var parts=line.trim().split(" +");String descriptor=parts[2];int close=descriptor.indexOf(')');
            var types=new Class<?>[close-1];var values=new Object[types.length];
            if(parts.length!=types.length+3)throw new IllegalArgumentException("Input arity mismatch");
            for(int i=0;i<types.length;i++) {
                long bits=Long.parseUnsignedLong(parts[i+3],16);
                switch(descriptor.charAt(i+1)) {
                    case 'I' -> {types[i]=int.class;values[i]=(int)bits;}
                    case 'J' -> {types[i]=long.class;values[i]=bits;}
                    case 'F' -> {types[i]=float.class;values[i]=Float.intBitsToFloat((int)bits);}
                    case 'D' -> {types[i]=double.class;values[i]=Double.longBitsToDouble(bits);}
                    default -> throw new IllegalArgumentException("Nonprimitive oracle signature");
                }
            }
            var method=Class.forName(parts[0]).getDeclaredMethod(parts[1],types);method.setAccessible(true);
            try {
                Object value=method.invoke(null,values);long bits;
                if(value instanceof Integer n)bits=Integer.toUnsignedLong(n);
                else if(value instanceof Long n)bits=n;
                else if(value instanceof Float n)bits=Integer.toUnsignedLong(Float.floatToIntBits(n));
                else if(value instanceof Double n)bits=Double.doubleToLongBits(n);
                else throw new IllegalStateException("Nonprimitive oracle return");
                System.out.printf("v %016x%n",bits);
            }catch(InvocationTargetException failure){System.out.println("e "+failure.getCause().getClass().getName());}
        }
    }
}
