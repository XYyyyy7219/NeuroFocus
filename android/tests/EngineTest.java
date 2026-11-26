package app.neurofocus.timer;
import java.util.*;

public final class EngineTest {
    static void check(boolean ok,String label){if(!ok)throw new AssertionError(label);}
    static class Log implements Engine.Sink {
        Map<String,Long> totals=new HashMap<>();
        Map<String,Integer> events=new HashMap<>();
        public void record(String k,long at,long ms){
            if(ms>0)totals.put(k,totals.getOrDefault(k,0L)+ms);
            else events.put(k,events.getOrDefault(k,0)+1);
        }
    }
    public static void main(String[] args){
        Engine e=new Engine(new Random(37));
        Log l=new Log();
        e.start(0,2,1,1,1,90,true,true,true);
        e.tick(60000,60000,l);check(e.phase.equals("micro")&&e.remaining()==60000,"micro clipped");
        e.tick(180000,180000,l);
        check(e.phase.equals("idle")&&l.totals.get("focus")==60000&&l.totals.get("micro")==60000&&l.totals.get("long")==60000,"inclusive totals");
        check(l.events.get("complete")==1&&l.events.get("micro_start")==1,"counts");
        e.start(0,2,1,1,1,10,true,false,false);
        l=new Log();e.tick(130000,130000,l);
        check(e.phase.equals("idle")&&l.totals.get("focus")==120000&&l.totals.get("micro")==10000,"exclusive totals");
        e.start(0,1,1,1,1,10,true,true,false);l=new Log();
        e.tick(60000,60000,l);check(!l.events.containsKey("micro_start")&&e.phase.equals("idle"),"tie");
        e.start(0,90,20,3,5,10,true,true,true);l=new Log();
        e.tick(1234,1234,l);e.paused=true;e.tick(999999,999999,l);e.paused=false;e.tick(1000125,1000125,l);
        check(e.used==1360,"pause/resume");
        Set<Long> picked=new HashSet<>();
        for(int i=0;i<500;i++){e.focus();check(e.left>=180000&&e.left<=300000,"interval bounds");picked.add(e.left);}
        check(picked.size()>450,"redraw");
        e.start(0,720,180,3,5,10,true,true,true);l=new Log();
        e.tick(1000000000L,1000000000L,l);
        check(e.phase.equals("idle")&&l.totals.get("focus")+l.totals.get("micro")==43200000&&l.totals.get("long")==10800000,"late callback");
        System.out.println("PASS: Android engine boundaries, independent accounting, random intervals, pause/resume and 12-hour catch-up.");
    }
}
