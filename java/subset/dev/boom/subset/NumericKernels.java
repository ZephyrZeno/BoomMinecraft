package dev.boom.subset;

/** Actual javac fixtures for the typed assembly backend, not a game runtime. */
public final class NumericKernels {
    public static long longConstant() { return 0xfedcba9876543210L; }
    public static double doubleConstant() { return -0x1.23456789abcdep-900; }
    public static float floatConstant() { return 0x1.fffffep-100f; }
    public static long longMix(long a,long b) { return ((a * 0x123456789abcdefL + b) ^ (a >>> 33)) - (b & 65535); }
    public static long longShift(long a,int count) { return (a << count) ^ (a >> count) ^ (a >>> count); }
    public static long longNeg(long a) { return -a; }
    public static int longCompare(long a,long b) { if(a<b)return -1;if(a>b)return 1;return 0; }
    public static long longDiv(long a,long b) { return a/b; }
    public static long longRem(long a,long b) { return a%b; }
    public static int intDiv(int a,int b) { return a/b; }
    public static int intRem(int a,int b) { return a%b; }
    public static long nestedDiv(long a,long b) { return longMix(longDiv(a,b),17L); }
    public static long longLoop(long a,int steps) { long sum=0;for(int i=0;i<steps;i++)sum=longMix(sum,a+i);return sum; }
    public static float floatMix(float a,float b,float c) { return (a+b)*c-a/b; }
    public static double doubleMix(double a,double b,double c) { return (a+b)*c-a/b; }
    public static float floatDiv(float a,float b) { return a/b; }
    public static double doubleDiv(double a,double b) { return a/b; }
    public static float floatNeg(float a) { return -a; }
    public static double doubleNeg(double a) { return -a; }
    public static int floatCompare(float a,float b) { if(a<b)return -1;if(a>b)return 1;if(a==b)return 0;return 7; }
    public static int doubleCompare(double a,double b) { if(a<b)return -1;if(a>b)return 1;if(a==b)return 0;return 7; }
    public static long i2l(int a) { return a; }
    public static float i2f(int a) { return a; }
    public static double i2d(int a) { return a; }
    public static int l2i(long a) { return (int)a; }
    public static float l2f(long a) { return a; }
    public static double l2d(long a) { return a; }
    public static int f2i(float a) { return (int)a; }
    public static long f2l(float a) { return (long)a; }
    public static double f2d(float a) { return a; }
    public static int d2i(double a) { return (int)a; }
    public static long d2l(double a) { return (long)a; }
    public static float d2f(double a) { return (float)a; }
    public static int narrowByte(int a) { return (byte)a; }
    public static int narrowChar(int a) { return (char)a; }
    public static int narrowShort(int a) { return (short)a; }
    public static long updateLong(long a) { long old=a++;return old^(a+=30000); }
    public static double updateDouble(double a) { double old=a++;return old+(a*=3); }
    public static double mixedCall(int a,long b,float c,double d) { return i2d(a)+l2d(b)+f2d(c)+d; }
    public static double manyArguments(int a,long b,float c,double d,int e,long f,float g,double h) { return mixedCall(a,b,c,d)-mixedCall(e,f,g,h); }
    public static long wideSwitch(int n,long value) { return switch(n) {case -1 -> value+1;case 0 -> value-1;case 1 -> value*3;default -> value^0x123456789abcdefL;}; }

    public static float unsupportedRemainder(float a,float b) { return a%b; }
    public static int unsupportedCatch(int a,int b) { try{return a/b;}catch(ArithmeticException ex){return 1;} }
    public static int unsupportedReference(Object a) { return a.hashCode(); }
    public static long recursiveLong(long a) { return a==0?0:recursiveLong(a-1); }
}
