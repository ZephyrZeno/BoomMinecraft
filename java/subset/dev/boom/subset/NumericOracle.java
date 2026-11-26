package dev.boom.subset;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class NumericOracle {
    public static void main(String[] args) throws Exception {
        var reader=new BufferedReader(new InputStreamReader(System.in));
        String line;
        while((line=reader.readLine())!=null) {
            var parts=line.trim().split(" +"); Method selected=null;
            for(var method:NumericKernels.class.getDeclaredMethods()) if(method.getName().equals(parts[0])) {selected=method;break;}
            if(selected==null)throw new IllegalArgumentException(parts[0]);
            var types=selected.getParameterTypes();if(types.length!=parts.length-1)throw new IllegalArgumentException(line);
            Object[] values=new Object[types.length];
            for(int i=0;i<types.length;i++) {
                long bits=Long.parseUnsignedLong(parts[i+1],16);
                if(types[i]==int.class)values[i]=(int)bits;
                else if(types[i]==long.class)values[i]=bits;
                else if(types[i]==float.class)values[i]=Float.intBitsToFloat((int)bits);
                else if(types[i]==double.class)values[i]=Double.longBitsToDouble(bits);
                else throw new IllegalArgumentException("Unsupported oracle signature");
            }
            try {
                Object value=selected.invoke(null,values);long bits;
                if(value instanceof Integer n)bits=Integer.toUnsignedLong(n);
                else if(value instanceof Long n)bits=n;
                else if(value instanceof Float n)bits=Integer.toUnsignedLong(Float.floatToIntBits(n));
                else if(value instanceof Double n)bits=Double.doubleToLongBits(n);
                else throw new IllegalStateException("Unsupported oracle return");
                System.out.printf("v %016x%n",bits);
            } catch(InvocationTargetException error) { System.out.println("e "+error.getCause().getClass().getName()); }
        }
    }
}
