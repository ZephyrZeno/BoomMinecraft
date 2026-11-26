package dev.boom.reflection;

import java.lang.reflect.Array;

// Bytecode fixture. All executed methods are translated by the MASM backend.
public final class ArrayReflection {
    public static int initialized;
    public interface Marker {}
    public static final class Element implements Marker { static { initialized++; } }

    public static Object allocate(Class<?> component, int length, int[] dims, int mode) {
        if (mode == 1) {
            if (component == null) return Object[][].class;
            if (length == 0) return Runnable[][].class;
            if (length == 1) return Marker[][].class;
            return Element[][][].class;
        }
        if (mode == 2) return ArrayBoundary.seed();
        try {
            if (mode == 4) return component.asSubclass(Object.class);
            if (mode == 5) return component.asSubclass(Element.class);
            if (mode == 6) return component.asSubclass(null);
            if (mode == 0) return Array.newInstance(component, length);
            return Array.newInstance(component, dims);
        } catch (NullPointerException e) {
            return e;
        } catch (NegativeArraySizeException e) {
            return e;
        } catch (IllegalArgumentException e) {
            return e;
        } catch (ClassCastException e) {
            return e;
        }
    }
}
