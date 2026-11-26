package app.neurofocus.timer;

import java.util.Random;

final class Engine {
    interface Sink {
        void record(String kind, long wall, long ms);
    }
    final Random rng;
    String phase = "idle";
    boolean paused, microOn, inclusive, autoLong;
    long used, left, last, target, longMs, microMs;
    int lo, hi;
    Engine(Random rng) { this.rng = rng; }

    void start(long now, int focus, int rest, int lower, int upper, int micro,
               boolean enabled, boolean counted, boolean auto) {
        target = focus * 60000L;
        longMs = rest * 60000L;
        lo = lower * 60000;
        hi = upper * 60000;
        microMs = micro * 1000L;
        microOn = enabled;
        inclusive = counted;
        autoLong = auto;
        used = 0;
        last = now;
        paused = false;
        focus();
    }
    void focus() {
        phase = "focus";
        left = microOn ? lo + rng.nextInt(hi - lo + 1) : target;
    }
    long remaining() {
        if (phase.equals("focus")) return target - used;
        if (phase.equals("micro") && inclusive) return Math.min(target - used, left);
        return left;
    }
    void tick(long now, long wall, Sink sink) {
        long elapsed = now - last;
        if (elapsed < 0) throw new IllegalArgumentException("clock");
        last = now;
        long cursor = wall - elapsed;
        while (!paused && elapsed > 0 && !phase.equals("idle")) {
            boolean counts = phase.equals("focus") || (phase.equals("micro") && inclusive);
            long step = Math.min(elapsed, Math.min(left, counts ? target - used : left));
            sink.record(phase, cursor, step);
            cursor += step;
            elapsed -= step;
            left -= step;
            if (counts) used += step;
            if (counts && used == target) {
                sink.record("complete", cursor, 0);
                phase = autoLong ? "long" : "idle";
                left = longMs;
                if (autoLong) sink.record("long_start", cursor, 0);
            } else if (left == 0) {
                if (phase.equals("focus")) {
                    phase = "micro";
                    left = microMs;
                    sink.record("micro_start", cursor, 0);
                } else if (phase.equals("micro")) {
                    focus();
                    sink.record("resume_focus", cursor, 0);
                } else {
                    phase = "idle";
                    sink.record("long_end", cursor, 0);
                }
            }
        }
    }
}
