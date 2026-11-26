import dev.boom.fields.ReflectionDispatchProgram;
public final class ReflectionDispatchReference {
    public static void main(String[] args) throws Exception {
        for (int mode = 0; mode < 12; mode++) System.out.println(ReflectionDispatchProgram.run(mode));
    }
}
