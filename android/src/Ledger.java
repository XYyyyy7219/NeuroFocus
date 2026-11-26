package app.neurofocus.timer;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.*;
import java.time.*;
import java.util.*;
import java.io.*;
import org.json.*;

final class Ledger extends SQLiteOpenHelper {
    private final TreeMap<String,long[]> pending = new TreeMap<>();
    long sid;
    Ledger(Context c) {
        super(c,"study.db",null,1);
        getWritableDatabase().execSQL("UPDATE session SET status='异常中断' WHERE status='进行中'");
    }
    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE session(id INTEGER PRIMARY KEY, start INTEGER, status TEXT)");
        db.execSQL("CREATE TABLE span(sid INTEGER, day TEXT, f INTEGER,m INTEGER,l INTEGER,n INTEGER,c INTEGER,PRIMARY KEY(sid,day))");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int oldV,int newV) { throw new IllegalStateException("未知数据格式"); }
    void begin(long wall) {
        android.content.ContentValues values=new android.content.ContentValues();
        values.put("start",wall);
        values.put("status","进行中");
        sid=getWritableDatabase().insertOrThrow("session",null,values);
    }
    private long[] row(String day) {
        long[] r=pending.get(day);
        if(r==null) { r=new long[5]; pending.put(day,r); }
        return r;
    }
    void add(String kind,long wall,long ms) {
        ZoneId zone=ZoneId.systemDefault();
        do {
            LocalDate day=Instant.ofEpochMilli(wall).atZone(zone).toLocalDate();
            long[] r=row(day.toString());
            if(ms==0) {
                if(kind.equals("micro_start")) r[3]++;
                if(kind.equals("complete")) r[4]++;
                break;
            }
            long midnight=day.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli();
            long step=Math.min(ms,midnight-wall);
            r[kind.equals("focus")?0:kind.equals("micro")?1:2]+=step;
            ms-=step;
            wall+=step;
        } while(ms>0);
    }
    void flush(String status) {
        if(sid==0) return;
        SQLiteDatabase db=getWritableDatabase();
        db.beginTransaction();
        try {
            for(Map.Entry<String,long[]> item:pending.entrySet()) {
                long[] r=item.getValue();
                db.execSQL("INSERT OR IGNORE INTO span VALUES(?,?,0,0,0,0,0)",new Object[]{sid,item.getKey()});
                db.execSQL("UPDATE span SET f=f+?,m=m+?,l=l+?,n=n+?,c=c+? WHERE sid=? AND day=?",
                           new Object[]{r[0],r[1],r[2],r[3],r[4],sid,item.getKey()});
            }
            if(status!=null) db.execSQL("UPDATE session SET status=? WHERE id=?",new Object[]{status,sid});
            db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
        pending.clear();
        if(status!=null) sid=0;
    }
    JSONObject stats() throws JSONException {
        JSONObject out=new JSONObject(),days=new JSONObject();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT day,sum(f),sum(m),sum(l),sum(n),sum(c) FROM span GROUP BY day",null)){
            while(c.moveToNext()){
                JSONArray vals=new JSONArray();
                for(int j=1;j<=5;j++) vals.put(c.getLong(j));
                days.put(c.getString(0),vals);
            }
        }
        JSONArray history=new JSONArray();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT start,status,ifnull(sum(f),0),ifnull(sum(m),0),ifnull(sum(l),0) FROM session LEFT JOIN span ON sid=id GROUP BY id ORDER BY id DESC LIMIT 100",null)){
            while(c.moveToNext()) history.put(new JSONArray().put(c.getLong(0)).put(c.getString(1)).put(c.getLong(2)).put(c.getLong(3)).put(c.getLong(4)));
        }
        return out.put("days",days).put("history",history);
    }
    void exportCsv(OutputStream stream) throws IOException {
        try(Writer w=new OutputStreamWriter(stream,"UTF-8");
            Cursor c=getReadableDatabase().rawQuery("SELECT id,start,status,day,f,m,l,n,c FROM session LEFT JOIN span ON sid=id ORDER BY id,day",null)){
            w.write("\uFEFF周期ID,开始时间,状态,日期,实际专注秒,微休息秒,长休息秒,微休息次数,完成周期数\r\n");
            while(c.moveToNext()){
                ZonedDateTime start=Instant.ofEpochMilli(c.getLong(1)).atZone(ZoneId.systemDefault());
                w.write(c.getLong(0)+","+start.toOffsetDateTime()+","+c.getString(2)+","+(c.isNull(3)?start.toLocalDate():c.getString(3))+","+c.getLong(4)/1000.0+","+c.getLong(5)/1000.0+","+c.getLong(6)/1000.0+","+c.getLong(7)+","+c.getLong(8)+"\r\n");
            }
        }
    }
}
