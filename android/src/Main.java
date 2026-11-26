package app.neurofocus.timer;

import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.*;
import android.webkit.*;
import android.widget.Toast;
import java.io.*;
import java.nio.charset.StandardCharsets;
import org.json.*;

public final class Main extends Activity {
    WebView web;
    TimerService service;
    boolean ready,visible;
    final Handler handler=new Handler(Looper.getMainLooper());
    final ServiceConnection connection=new ServiceConnection(){
        public void onServiceConnected(ComponentName n,IBinder binder){service=((TimerService.Local)binder).service(); render(true);}
        public void onServiceDisconnected(ComponentName n){service=null;}
    };
    final Runnable pulse=new Runnable(){public void run(){if(visible){render(false);handler.postDelayed(this,500);}}};
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(20,49,39));
        getWindow().setNavigationBarColor(Color.rgb(20,49,39));
        web=new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setBlockNetworkLoads(true);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){return true;}
            @Override public void onPageFinished(WebView v,String u){ready=true;render(true);}
        });
        web.addJavascriptInterface(new Bridge(),"Mobile");
        setContentView(web);
        try(InputStream in=getAssets().open("mobile.html"); ByteArrayOutputStream buf=new ByteArrayOutputStream()){
            byte[] chunk=new byte[8192];int n;
            while((n=in.read(chunk))!=-1)buf.write(chunk,0,n);
            web.loadDataWithBaseURL("https://neurofocus.invalid/",new String(buf.toByteArray(),StandardCharsets.UTF_8),"text/html","UTF-8",null);
        }catch(IOException e){throw new IllegalStateException(e);}
        bindService(new Intent(this,TimerService.class),connection,BIND_AUTO_CREATE);
    }
    @Override public void onResume(){super.onResume();visible=true;handler.post(pulse);}
    @Override public void onPause(){visible=false;handler.removeCallbacks(pulse);super.onPause();}
    @Override public void onDestroy(){unbindService(connection);web.removeJavascriptInterface("Mobile");web.destroy();super.onDestroy();}
    void render(boolean full){
        if(!ready || service==null || isFinishing())return;
        try{
            Engine e=service.timer;
            JSONObject s=new JSONObject();
            s.put("phase",e.phase).put("paused",e.paused).put("remaining",e.phase.equals("idle")?service.prefs.getInt("focus",90)*60000L:e.remaining());
            s.put("progress",e.phase.equals("idle")?0:(double)e.used/e.target).put("message",service.message);
            if(full){s.put("prefs",new JSONObject(service.prefs.getAll()));s.put("stats",service.ledger.stats());}
            web.evaluateJavascript("window.render("+s+")",null);
        }catch(JSONException e){toast("无法显示记录");}
    }
    void toast(String s){Toast.makeText(this,s,Toast.LENGTH_SHORT).show();}
    final class Bridge {
        @JavascriptInterface public void command(String command){runOnUiThread(()->{
            if(service==null)return;
            switch(command){
            case "start":
                if(Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=PackageManager.PERMISSION_GRANTED
                    && !service.prefs.getBoolean("asked",false)){
                    service.prefs.edit().putBoolean("asked",true).apply();
                    requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},1);
                }
                if(service.timer.phase.equals("idle"))startForegroundService(new Intent(Main.this,TimerService.class).setAction("start"));
                break;
            case "toggle":service.step("toggle");break;
            case "end":case "reset":
                new AlertDialog.Builder(Main.this).setMessage((command.equals("end")?"结束":"重置")+"本轮？已经学习的时间会保留。")
                    .setNegativeButton("取消",null).setPositiveButton("确定",(d,w)->{if(service!=null){service.step(command);render(true);}}).show();
                break;
            case "refresh":service.step("flush");break;
            case "preview":service.chime("micro_start");break;
            case "export":
                startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("text/csv").putExtra(Intent.EXTRA_TITLE,"NeuroFocus-学习记录.csv"),20);break;
            }
            render(true);
        });}
        @JavascriptInterface public void setting(String key,String value){runOnUiThread(()->{
            if(service==null)return;
            SharedPreferences.Editor edit=service.prefs.edit();
            int lo=1,hi;
            switch(key){
                case "focus":hi=720;break;case "long":hi=180;break;case "micro":hi=300;break;
                case "low":case "high":hi=120;break;case "volume":lo=0;hi=100;break;
                case "auto_long":case "inclusive":case "micro_on":case "dark":case "audio":case "notify":
                    edit.putBoolean(key,value.equals("true")).apply();render(true);return;
                default:return;
            }
            try{
                int v=Integer.parseInt(value);
                if(v<lo||v>hi)throw new NumberFormatException();
                if(key.equals("low")&&v>service.prefs.getInt("high",5))edit.putInt("high",v);
                if(key.equals("high")&&v<service.prefs.getInt("low",3))edit.putInt("low",v);
                edit.putInt(key,v).apply();
            }catch(NumberFormatException err){toast("请输入 "+lo+" 到 "+hi+" 之间的整数");}
            render(true);
        });}
    }
    @Override public void onActivityResult(int code,int result,Intent data){
        super.onActivityResult(code,result,data);
        if(code==20 && result==RESULT_OK && data!=null && data.getData()!=null && service!=null){
            service.step("flush");
            try(OutputStream stream=getContentResolver().openOutputStream(data.getData(),"wt")){
                if(stream==null)throw new IOException();
                service.ledger.exportCsv(stream);toast("学习记录已导出");
            }catch(IOException|RuntimeException e){toast("导出失败，请选择可写入的位置");}
        }
    }
}
