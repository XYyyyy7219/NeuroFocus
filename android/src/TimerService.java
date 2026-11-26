package app.neurofocus.timer;

import android.app.*;
import android.content.*;
import android.database.sqlite.SQLiteException;
import android.media.*;
import android.os.*;
import java.util.Random;
import org.json.*;

public final class TimerService extends Service {
    final Engine timer=new Engine(new Random());
    final Handler handler=new Handler(Looper.getMainLooper());
    final class Local extends Binder { TimerService service() { return TimerService.this; } }
    final Local binder=new Local();
    Ledger ledger;
    SharedPreferences prefs;
    NotificationManager notices;
    PowerManager.WakeLock lock;
    ToneGenerator sound;
    long saved;
    String message="",lastEvent="",pendingEnd=null;
    static final String CHANNEL="focus_timer";
    @Override public void onCreate(){
        super.onCreate();
        prefs=getSharedPreferences("settings",MODE_PRIVATE);
        ledger=new Ledger(this);
        notices=getSystemService(NotificationManager.class);
        notices.createNotificationChannel(new NotificationChannel(CHANNEL,"专注计时",NotificationManager.IMPORTANCE_LOW));
        lock=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"NeuroFocus:session");
        lock.setReferenceCounted(false);
    }
    @Override public IBinder onBind(Intent i){ return binder; }
    String stage(){
        switch(timer.phase){
            case "focus": return "专注中";
            case "micro": return "微休息";
            case "long": return "长休息";
            default: return "待机";
        }
    }
    Notification notification(){
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,Main.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b=new Notification.Builder(this,CHANNEL)
            .setSmallIcon(R.drawable.mark).setContentTitle("NeuroFocus · "+stage())
            .setContentText(timer.paused?"已暂停 · 点按返回":"点按返回专注计时")
            .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true);
        if(!timer.paused && !timer.phase.equals("idle"))
            b.setWhen(System.currentTimeMillis()+timer.remaining()).setUsesChronometer(true).setChronometerCountDown(true);
        return b.build();
    }
    @Override public int onStartCommand(Intent intent,int flags,int id){
        startForeground(1,notification());
        if(timer.phase.equals("idle") && ledger.sid==0 && intent!=null && "start".equals(intent.getAction())){
            long now=SystemClock.elapsedRealtime();
            try{
                ledger.begin(System.currentTimeMillis());
                timer.start(now,prefs.getInt("focus",90),prefs.getInt("long",20),
                    prefs.getInt("low",3),prefs.getInt("high",5),prefs.getInt("micro",10),
                    prefs.getBoolean("micro_on",true),prefs.getBoolean("inclusive",true),prefs.getBoolean("auto_long",true));
                saved=now; message="";
                keepAwake();
                notices.notify(1,notification());
                schedule();
            }catch(SQLiteException error){message="无法保存学习记录，请检查存储空间"; stopForeground(STOP_FOREGROUND_REMOVE); stopSelf();}
        } else if(timer.phase.equals("idle")){stopForeground(STOP_FOREGROUND_REMOVE); stopSelf();}
        return START_NOT_STICKY;
    }
    void keepAwake(){
        if(lock.isHeld()) lock.release();
        if(!timer.paused && !timer.phase.equals("idle")) lock.acquire(Math.min(timer.left,timer.remaining())+60000);
    }
    private final Runnable pulse=new Runnable(){@Override public void run(){ step(null); schedule(); }};
    private void schedule(){
        handler.removeCallbacks(pulse);
        if(!timer.paused && !timer.phase.equals("idle"))
            handler.postDelayed(pulse,Math.max(1,Math.min(1000,Math.min(timer.left,timer.remaining()))));
    }
    void step(String action){
        if(ledger.sid==0)return;
        long now=SystemClock.elapsedRealtime(), wall=System.currentTimeMillis();
        lastEvent="";
        try {
            timer.tick(now,wall,(kind,at,ms)->{ledger.add(kind,at,ms); if(ms==0)lastEvent=kind;});
            if(pendingEnd==null){
                if(timer.phase.equals("idle")) pendingEnd="已完成";
                else if("end".equals(action))pendingEnd="手动结束";
                else if("reset".equals(action))pendingEnd="已重置";
            }
            if("toggle".equals(action)) timer.paused=!timer.paused;
            if(pendingEnd!=null || action!=null || !lastEvent.isEmpty() || now-saved>=5000){
                ledger.flush(pendingEnd);
                saved=now;
            }
        }catch(SQLiteException error){
            timer.paused=true;
            message="记录写入失败，已暂停。请释放空间后重试。";
            keepAwake();
            notices.notify(1,notification());
            return;
        }
        if(!lastEvent.isEmpty()){
            chime(lastEvent);
            if(lastEvent.equals("micro_start"))message="放松，自然休息";
            else if(lastEvent.equals("resume_focus"))message="继续学习";
            else if(lastEvent.equals("long_start"))message="专注周期已完成";
            else message="本轮已完成，可开始下一轮";
        }
        if(pendingEnd!=null){
            if(lastEvent.isEmpty())message=pendingEnd+"，学习记录已保存";
            timer.phase="idle"; timer.paused=false; pendingEnd=null;
            handler.removeCallbacks(pulse);
            keepAwake();
            stopForeground(STOP_FOREGROUND_REMOVE);
            if((lastEvent.equals("complete")||lastEvent.equals("long_end")) && prefs.getBoolean("notify",true)){
                PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,Main.class),PendingIntent.FLAG_IMMUTABLE);
                notices.notify(2,new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.mark)
                    .setContentTitle("NeuroFocus").setContentText(message).setAutoCancel(true).setContentIntent(open).build());
            }
            stopSelf();
        } else if(!lastEvent.isEmpty() || "toggle".equals(action)){
            keepAwake(); notices.notify(1,notification()); schedule();
        }
    }
    void chime(String event){
        if(!prefs.getBoolean("audio",true) || prefs.getInt("volume",45)==0)return;
        int code=event.equals("micro_start")?ToneGenerator.TONE_PROP_ACK:
            event.equals("resume_focus")?ToneGenerator.TONE_PROP_BEEP:
            event.equals("long_start")?ToneGenerator.TONE_PROP_BEEP2:ToneGenerator.TONE_PROP_PROMPT;
        try{
            if(sound!=null)sound.release();
            sound=new ToneGenerator(AudioManager.STREAM_MUSIC,prefs.getInt("volume",45));
            sound.startTone(code,260);
        }catch(RuntimeException e){message="提示音暂不可用";}
    }
    @Override public void onDestroy(){
        handler.removeCallbacks(pulse);
        if(lock.isHeld())lock.release();
        if(sound!=null)sound.release();
        if(ledger.sid!=0){step("end");}
        ledger.close();
        super.onDestroy();
    }
}
