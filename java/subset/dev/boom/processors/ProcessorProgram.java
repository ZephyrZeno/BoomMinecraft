package dev.boom.processors;
public final class ProcessorProgram {
    public static int count(int mode) {
        Runtime runtime = mode == 2 ? null : Runtime.getRuntime();
        try {
            int count = runtime.availableProcessors();
            if (mode == 1) return runtime == Runtime.getRuntime() && count > 0 ? count : -1;
            if (mode == 3) { for(int i=0;i<7;i++) if(runtime.availableProcessors()!=count)return -2; }
            return count;
        } catch(NullPointerException e) { return -4; }
    }
    public static long memory(int mode) {
        Runtime runtime = mode == 4 ? null : Runtime.getRuntime();
        try {
            if(mode==0)return runtime.maxMemory();
            if(mode==1)return runtime.totalMemory();
            if(mode==2)return runtime.freeMemory();
            long max=runtime.maxMemory(),total=runtime.totalMemory(),free=runtime.freeMemory();
            return max>0 && total>0 && free>=0 && free<=total && total<=max ? 1 : 0;
        } catch(NullPointerException e) {return -4;}
    }
    public static int uncaught(Runtime runtime) { return runtime.availableProcessors(); }
}
