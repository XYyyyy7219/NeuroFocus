"""Check the released views with disposable SQLite data and native window screenshots."""
import argparse
import sys
import tempfile
import time
from datetime import datetime,timedelta
from pathlib import Path
from statistics import median
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from neurofocus.clock import WindowsClock
from neurofocus.storage import Store
from neurofocus.controller import Controller
from neurofocus.config import Settings
from neurofocus.window import Window
from neurofocus.starlight import texture


def seed(store,n):
    db=store.db
    names=("理论力学","Python","数学","英语")
    topics=("拉格朗日方程","数据结构","解析函数","学术写作")
    tags=[store.tags.save(name,color) for name,color in zip(names,("#edb679","#89c9d1","#be9dde","#87c5a4"))]
    start=datetime(2024,1,1,8)
    with db:
        for i in range(n):
            at=start+timedelta(hours=i*.75)
            stamp=int(at.timestamp()*1000)
            ms=(9+i%35)*60000
            day=str(at.date())
            tag=tags[i%4]
            sid=i+1
            db.execute("INSERT INTO sessions VALUES(?,?,?,'ended')",(sid,stamp,stamp+ms))
            db.execute("INSERT INTO days VALUES(?,?,?,0,0,0,0)",(sid,day,ms))
            db.execute("INSERT INTO focus_spans VALUES(?,?,0,?,?,?,?)",(sid,day,tag,stamp,stamp+ms,ms))
            if i%3:
                db.execute("INSERT INTO journal VALUES(?,?,0,?,?,?,?,?,?,?)",
                           (sid,day,tag,topics[i%4],"已完成例题并复核推导。","","从下一节继续","",stamp+ms))


def run(app,output,n):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        store=Store(root/"test.db")
        seed(store,n)
        w=Window(Controller(store,root/"config.json",Settings(audio=False),WindowsClock()))
        try:
            w.resize(1100,710)
            w.show()
            app.processEvents()
            h=w.archive
            begin=time.perf_counter()
            w.navigate(3)
            h.tabs.setCurrentIndex(2)
            app.processEvents()
            entry=(time.perf_counter()-begin)*1000
            assert h.stage.isVisible() and len(h.cut_rows)==n
            assert not texture("spiral.png").isNull()
            assert h.sky.size()==w.centralWidget().size()
            assert w.grab().save(str(output/f"sky-{n}.png"))
            paint=[]
            calls=[]
            store.db.set_trace_callback(calls.append)
            for _ in range(9):
                start=time.perf_counter()
                h.sky.viewport().grab()
                paint.append(1000*(time.perf_counter()-start))
            store.db.set_trace_callback(None)
            assert not calls
            if n>=112:
                a=next(a for a in h.cut_rows if a.note[0])
                h.sky.enter((a.tag,a.note[0],a.key))
                QTest.qWait(300)
                assert h.stage.panel.isVisible()
                if n==112:
                    assert w.grab().save(str(output/"selected-activity.png"))
                leaves=len(h.sky.nodes)
            else: leaves=0
            print(f"{n} activities | {entry:.1f} ms first archive+overview | {median(paint):.2f} ms warm viewport grab | "
                  f"{leaves} bodies on inspected topic | {len(calls)} paint queries")
        finally:
            w.close()
            store.db.close()
            app.processEvents()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([])
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    for n in (3,112,20000): run(app,args.output,n)
