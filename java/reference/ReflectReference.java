import dev.boom.reflect.ReflectProgram;
public final class ReflectReference {
    public static void main(String[] args) throws Exception {
        for(int kind=0;kind<=11;kind++)for(int route=0;route<3;route++){
            try{
                Object value=ReflectProgram.run(kind,route,1);
                int n=0;
                if(value.getClass()!=Object.class){var f=value.getClass().getDeclaredField("value");f.setAccessible(true);n=f.getInt(value);}
                System.out.println(kind+" "+route+" v "+value.getClass().getName()+" "+n);
            }catch(Throwable e){System.out.println(kind+" "+route+" e "+e.getClass().getName()+" "+(e.getCause()==null?"-":e.getCause().getClass().getName()));}
        }
    }
}
