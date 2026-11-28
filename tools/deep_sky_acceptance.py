"""Windows native acceptance. All sessions, journals and exports live in temporary databases."""
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime,timedelta
import json
import os
from pathlib import Path
from statistics import median
import sys
import tempfile
from time import perf_counter,process_time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject,QEvent,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from neurofocus.clock import WindowsClock
from neurofocus.config import Settings
from neurofocus.controller import Controller
from neurofocus.storage import Store
from neurofocus.window import Window


def memory_mb():
    class Memory(C.Structure):
        _fields_=[("size",W.DWORD),("faults",W.DWORD)]+[(name,C.c_size_t) for name in
            ("peak","working","paged_peak","paged","nonpaged_peak","nonpaged","pagefile","pagefile_peak")]
    m=Memory()
    m.size=C.sizeof(m)
    assert C.windll.psapi.GetProcessMemoryInfo(W.HANDLE(-1),C.byref(m),m.size)
    return round(m.working/1048576,1)


class Gpu:
    """Read the busiest engine instance owned by this process, where available."""
    class Value(C.Structure):
        _fields_=[("status",W.DWORD),("value",C.c_double)]
    def __init__(self):
        self.api=C.windll.pdh
        self.system_peak=None
        self.instances=0
        self.query=C.c_void_p()
        self.counter=C.c_void_p()
        status=self.api.PdhOpenQueryW(None,0,C.byref(self.query))
        self.ready=not status and not self.api.PdhAddEnglishCounterW(self.query,
            r"\GPU Engine(*)\Utilization Percentage",0,C.byref(self.counter))
        if self.ready: self.api.PdhCollectQueryData(self.query)
    def read(self):
        class Item(C.Structure):
            _fields_=[("name",W.LPWSTR),("value",Gpu.Value)]
        if not self.ready: return None
        self.api.PdhCollectQueryData(self.query)
        size,count=W.DWORD(),W.DWORD()
        fn=self.api.PdhGetFormattedCounterArrayW
        fn(self.counter,0x200,C.byref(size),C.byref(count),None)
        if not size.value: return None
        buf=C.create_string_buffer(size.value)
        if fn(self.counter,0x200,C.byref(size),C.byref(count),buf): return None
        items=C.cast(buf,C.POINTER(Item))
        valid=[items[i].value.value for i in range(count.value) if items[i].value.status<2]
        self.instances=len(valid)
        self.system_peak=round(max(valid),3) if valid else None
        matches=[items[i].value.value for i in range(count.value) if items[i].value.status<2
                 and items[i].name.startswith(f"pid_{os.getpid()}_")]
        return round(max(matches),3) if matches else None
    def close(self):
        if self.query: self.api.PdhCloseQuery(self.query)


class Frames(QObject):
    def __init__(self):
        super().__init__()
        self.count=0
    def eventFilter(self,obj,e):
        if e.type()==QEvent.Paint: self.count+=1
        return False


def seed(store,n):
    tags=[store.tags.save(name,c) for name,c in (("理论力学","#edb478"),("py","#79c6df"),
        ("英语","#adc892"),("量子物理","#c29cdd"),("数学","#82bab5"))]
    stamp0=datetime(2023,10,2,8)
    topics=("拉格朗日方程","广义坐标","守恒量","小振动","正则变换","解析力学")
    with store.db as db:
        for i in range(n):
            k=i%12
            tag=tags[0 if k<5 else 1 if k<8 else 2 if k<10 else k-7]
            at=(stamp0+timedelta(days=i*790//max(1,n))).replace(hour=7+i%13)
            stamp=round(at.timestamp()*1000)
            day=str(at.date())
            ms=(3+(i*17)%57)*60000
            sid=i+1
            db.execute("INSERT INTO sessions VALUES(?,?,?,'ended')",(sid,stamp,stamp+ms+10000))
            db.execute("INSERT INTO days VALUES(?,?,?,10000,0,1,0)",(sid,day,ms))
            db.execute("INSERT INTO focus_spans VALUES(?,?,0,?,?,?,?)",(sid,day,tag,stamp,stamp+ms,ms))
            db.execute("INSERT INTO session_protocol VALUES(?,?,0)",(sid,json.dumps({"focus":90,"long":20,
                "low":3,"high":5,"micro":10,"inclusive":True,"auto_long":True,"micro_on":True})))
            if i%4!=3:
                topic=topics[(i//12+i)%6] if tag==tags[0] else ("递归与模块" if tag==tags[1] else "章节回顾")
                db.execute("INSERT INTO journal VALUES(?,?,0,?,?,?,?,?,?,?)",(sid,day,tag,topic,"独立推导并用例题核对结果。",
                    "边界条件变化时是否仍然成立？","回到第三章的例题。","投入",stamp+ms))
    store.tags.save("英语阅读","#adc892",tags[2])
    store.tags.archive(tags[2],True)


def run(app,dest,n):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        store=Store(root/"fixture.sqlite3")
        seed(store,n)
        clock=WindowsClock()
        ctrl=Controller(store,root/"settings.json",Settings(audio=False),clock)
        w=Window(ctrl)
        gpu=None
        try:
            w.resize(1120,735)
            w.show()
            app.processEvents()
            h=w.archive
            sky=h.sky
            start=perf_counter()
            w.navigate(3)
            h.tabs.setCurrentIndex(2)
            app.processEvents()
            load_ms=round(1000*(perf_counter()-start),1)
            sky.set_low(True)
            def snap(name):
                app.processEvents()
                assert w.grab().save(str(dest/(name+".png")))
            snap(f"overview-{n}")
            assert len(h.cut_rows)==n
            times=[]
            for i in range(9):
                start=perf_counter()
                sky.viewport().grab()
                times.append(1000*(perf_counter()-start))
            result=dict(records=n,load_ms=load_ms,grab_ms=round(median(times),2),working_mb=memory_mb())
            if n==100:
                a=next(a for a in h.cut_rows if a.note[0])
                scope=(a.tag,a.note[0])
                sky.set_low(False)
                sky.enter(scope[:1])
                assert sky._camera.state().value
                QTest.qWait(335)
                assert not sky._camera.state().value
                snap("galaxy")
                sky.set_low(True)
                sky.enter(scope); snap("cluster")
                node=sky.nodes[scope+(a.key,)]
                for name,scale in (("lod-0",.22),("lod-1",1.),("lod-2",3.8)):
                    sky.focus_camera(node.pos(),scale,False)
                    snap(name)
                sky.enter(scope+(a.key,)); snap("observation")
                sky.ascend()
                sky.enter(())
                h.stage.search.setText("小振动")
                h.stage.apply_search(True)
                assert h.items[sky.selected].note[0]=="小振动"
                h.stage.search.setText("")
                h.stage.apply_search()
                h.tag.setCurrentIndex(h.tag.findData(a.tag))
                assert h.cut_rows and all(row.tag==a.tag for row in h.cut_rows)
                h.tag.setCurrentIndex(0)
                h.slide.setValue(0)
                assert len(h.cut_rows)<n
                h.slide.setValue(h.slide.maximum())
                assert len(h.cut_rows)==n
            if n==10000:
                from collections import Counter
                path,members=Counter((a.tag,a.note[0]) for a in h.cut_rows).most_common(1)[0]
                sky.enter(path)
                assert len(sky.nodes)==members
                result["pan_topic_members"]=members
                frames=Frames()
                sky.viewport().installEventFilter(frames)
                gpu=Gpu()
                c0=process_time(); t0=perf_counter()
                QTest.qWait(1300)
                result["idle_cpu_core_pct"]=round(100*(process_time()-c0)/(perf_counter()-t0),2)
                result["idle_gpu_engine_pct"]=gpu.read()
                result["idle_system_busiest_gpu_instance_pct"]=gpu.system_peak
                cpu=process_time(); start=perf_counter(); frames.count=0
                ref=clock.sample()[0]; ctrl.start()
                while perf_counter()-start<2.4:
                    t=perf_counter()-start
                    sky.centerOn(QPointF(t*290,110))
                    QTest.qWait(12)
                ctrl.update("ended"); elapsed=clock.sample()[0]-ref
                dt=perf_counter()-start
                result.update(pan_paints_s=round(frames.count/dt,1),
                    pan_cpu_core_pct=round(100*(process_time()-cpu)/dt,2),
                    pan_gpu_engine_pct=gpu.read(),pan_seconds=round(dt,3),timer_ref_ms=elapsed,
                    timer_record_ms=store.history(limit=1)[0][2],working_topic_mb=memory_mb())
                result["pan_system_busiest_gpu_instance_pct"]=gpu.system_peak
                result["valid_gpu_instances"]=gpu.instances
                w.showMinimized()
                app.processEvents(); frames.count=0
                t0=perf_counter(); c0=process_time(); QTest.qWait(1100)
                result["minimized_cpu_core_pct"]=round(100*(process_time()-c0)/(perf_counter()-t0),2)
                result["minimized_paints"]=frames.count
            return result
        finally:
            if gpu: gpu.close()
            w.close(); store.db.close(); app.processEvents()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--count",type=int)
    args=parser.parse_args()
    args.output.mkdir(exist_ok=True,parents=True)
    if args.count is not None:
        app=QApplication([])
        app.setStyle("Fusion")
        app.setQuitOnLastWindowClosed(False)
        print(json.dumps(run(app,args.output,args.count)),flush=True)
        sys.exit(0)
    import subprocess
    results=[]
    for n in (0,1,10,100,1000,10000):
        payload=subprocess.check_output([sys.executable,__file__,"--output",str(args.output),"--count",str(n)],text=True)
        row=json.loads(payload)
        print(row,flush=True)
        results.append(row)
    (args.output/"measurements.json").write_text(json.dumps(results,indent=2),encoding="utf8")
