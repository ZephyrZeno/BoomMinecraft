// Locked JVM comparison only; never part of the native game runtime.
public final class ModuleObjectsReference {
    public static void main(String[] args) throws Exception {
        var ctor = Module.class.getDeclaredConstructor(ClassLoader.class);
        ctor.setAccessible(true);
        var loader = new ClassLoader() {};
        for (int i = 0; i < 256; i++) {
            Module empty = ctor.newInstance(new Object[]{null});
            Module unnamed = ctor.newInstance(loader);
            if (empty.isNamed() || empty.getName() != null || empty.getClassLoader() != null || empty.getLayer() != null
                    || unnamed.isNamed() || unnamed.getName() != null || unnamed.getClassLoader() != loader || unnamed.getLayer() != null)
                throw new AssertionError("Original unnamed Module constructor");
        }
        if (Object.class.getModule().getLayer() != ModuleLayer.boot()) throw new AssertionError("Boot identity");
        System.out.println("constructor_cases=512;physical_fields=4;boot_identity=true");
    }
}
