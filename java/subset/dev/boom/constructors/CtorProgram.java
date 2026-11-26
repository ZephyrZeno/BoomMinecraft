package dev.boom.constructors;
import java.lang.reflect.Constructor;
public final class CtorProgram {
 public static class Target { public long score; static {Counters.mask|=1;Counters.count++;} public Target(){score=42;} public Target(int n)throws java.io.IOException{score=n;} protected Target(long n){score=n+1;} private Target(double d){score=(long)d;} }
 public static class Private {public long score;private Private(){score=73;}}
 public abstract static class Abstract {public Abstract(){Counters.mask|=4;}}
 public static class Marker extends RuntimeException {public final int value;public Marker(int value){this.value=value;}}
 public static class Throwing {public Throwing(){throw new Marker(5);}}
 public static class BadInit {static {Counters.mask|=8;if(fail())throw new Marker(9);}static boolean fail(){return true;}public BadInit(){}}
 public static class Args {public long score;public Object ref;public Args(boolean z,byte b,char c,short s,int i,long j,float f,double d,Object ref,int[] array){this.ref=ref;score=(z?1:0)+b*3L+c*5L+s*7L+i*11L+j*13L+(long)(f*17)+(long)(d*19)+(array==null?23:array.length*23L)+(ref==null?29:31);}}
 public static class Wide {public long score;public Wide(int a0,int a1,int a2,int a3,int a4,int a5,int a6,int a7,int a8,int a9,int a10,int a11,int a12,int a13,int a14,int a15,int a16){score=1L*a0+3L*a1+5L*a2+7L*a3+9L*a4+11L*a5+13L*a6+15L*a7+17L*a8+19L*a9+21L*a10+23L*a11+25L*a12+27L*a13+29L*a14+31L*a15+33L*a16;}}
 public static class Ref {public long score;public Object ref;public Ref(String value){ref=value;score=value==null?11:value.length();}public Ref(Object value,int[] data){ref=value;score=data==null?13:data.length;}}
 public static class Generic {public long score;@Deprecated public <T> Generic(@Deprecated T value)throws java.io.IOException{score=89;}}
 public static class NoZero {public NoZero(int value){}}
 public static class Vargs {public long score;public Vargs(int... values){score=values==null?7:values.length;}}
 public enum EnumValue {A;static{Counters.mask|=16;}}
 public static Class<?> type(int kind){return switch(kind){case 0->Target.class;case 1->Private.class;case 2->Abstract.class;case 3->Throwing.class;case 4->BadInit.class;case 5->Args.class;case 6->Wide.class;case 7->Ref.class;case 8->int.class;case 9->int[].class;case 10->NoZero.class;case 11->EnumValue.class;case 12->String.class;case 13->Vargs.class;case 15->Generic.class;default->Object.class;};}
 public static Object run(int operation,int kind,Class<?>[] parameters,Object[] arguments,boolean outside,Constructor<?> supplied)throws Exception {
  Constructor<?> constructor=operation>=2?supplied:type(kind).getDeclaredConstructor(parameters);
  if(operation==0)return constructor;
  if(operation==1||operation==2)return outside?OtherCaller.invoke(constructor,arguments):constructor.newInstance(arguments);
  if(operation==3)return constructor.getDeclaringClass();
  if(operation==4)return constructor.getParameterTypes();
  if(operation==5)return constructor.getExceptionTypes();
  if(operation==6)return constructor.getName();
  if(operation==7)return type(kind).getConstructor(parameters);
  return new int[]{constructor.getModifiers(),constructor.getParameterCount(),constructor.isVarArgs()?1:0,constructor.isSynthetic()?1:0,constructor.hashCode(),constructor.equals(arguments==null?null:arguments[0])?1:0};
 }
}
