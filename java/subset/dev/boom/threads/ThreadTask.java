package dev.boom.threads;

/** AOT guest workload; this is not a substitute java.lang.Thread class. */
public final class ThreadTask {
    public static final class State {
        public final int index, divisor;
        public long answer;
        public int failures, exits;
        public long returned, check;
        public State(int index,int divisor){this.index=index;this.divisor=divisor;}
    }
    public static State create(int index,int divisor){return new State(index,divisor);}
    public static long run(State state){
        long value=0x123456789abcdef0L;
        for(int i=0;i<257*((state.index&7)+1);i++)value=value*6364136223846793005L+state.index+i;
        state.answer=value;
        return value/state.divisor;
    }
    public static int onFailure(State state){return ++state.failures;}
    public static int onExit(State state){return ++state.exits;}
    public static long summary(State state){return state.answer^((long)state.exits<<32)^state.failures;}
    public static State execute(int operation,State state,int index,int divisor){
        switch(operation){
            case 0: return create(index,divisor);
            case 1: state.returned=run(state);break;
            case 2: onFailure(state);break;
            case 3: onExit(state);break;
            case 4: state.check=summary(state);break;
            default: break;
        }
        return state;
    }
}
