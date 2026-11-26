package dev.boom.mirrors;
class ClassState {
    static Class<?> value = java.io.File.class;
    static Class<?>[] values = {value, Child.class, int[][].class, ClassFailure.class};
}
