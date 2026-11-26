package dev.boom.notifications;
public final class NotifyProgram {
    static final class Lock { }
    public static int run(int op) {
        Object value = op == 3 ? null : op == 4 ? new int[0] : op == 5 ? NotifyProgram.class : op == 6 ? "monitor" : new Lock();
        try {
            switch(op) {
                case 0: value.notify(); return 10;
                case 1: synchronized(value) { value.notify(); return 11; }
                case 2: synchronized(value) { synchronized(value) { value.notifyAll(); } value.notify(); return 12; }
                case 3: value.notifyAll(); return 13;
                case 4: case 5: case 6: synchronized(value) { value.notifyAll(); return 14+op; }
                case 7: new Lock().notifyAll(); return 17;
                case 8: synchronized(value) { value.notifyAll(); throw new IllegalStateException(); }
                default: synchronized(value) { value.notifyAll(); } return 19;
            }
        } catch (NullPointerException e) {return -4;}
          catch (IllegalMonitorStateException e) {return -17;}
          catch (IllegalStateException e) {return -1;}
    }
    public static void fail(Object value) { value.notifyAll(); }
}
