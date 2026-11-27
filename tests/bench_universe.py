"""Run on Windows from the repository root; all records are synthetic and in memory."""
import os
import sys
from pathlib import Path
from statistics import median
from time import perf_counter
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication
from neurofocus.history import activities
from neurofocus.storage import Store
from neurofocus.universe import Sky,layout_slots


def main():
    app=QApplication([])
    store=Store(":memory:")
    tags=[store.tags.save(f"科目 {i+1}","#86b5ae") for i in range(10)]
    db=store.db
    base=date(2024,1,1)
    size=20000
    with db:
        db.executemany("INSERT INTO sessions VALUES(?,0,600000,'ended')",((i,) for i in range(1,size+1)))
        db.executemany("INSERT INTO focus_spans VALUES(?,?,0,?,0,600000,600000)",
                       ((i,str(base+timedelta(days=i//30)),tags[i%10]) for i in range(1,size+1)))
    timings=[]
    for _ in range(5):
        start=perf_counter()
        rows=activities(db)
        slots=layout_slots(rows)
        timings.append(1000*(perf_counter()-start))
    sky=Sky()
    sky.resize(900,500)
    sky.show()
    sky.populate(rows,{t.id:t for t in store.tags.all()},slots,True)
    assert len(sky.nodes)==10
    start=perf_counter()
    sky.enter((tags[0],""))
    scene=1000*(perf_counter()-start)
    assert len(sky.nodes)==2000
    app.processEvents()
    paint=[]
    sql=[]
    db.set_trace_callback(sql.append)
    for i in range(11):
        sky.centerOn(i*15,i*5)
        start=perf_counter()
        assert not sky.grab().isNull()
        paint.append(1000*(perf_counter()-start))
    assert not sql
    print(f"{size} activities / 10 subjects / 2000 visible-level stars; projection+slots median {median(timings):.2f} ms; "
          f"scene entry {scene:.2f} ms; 900x500 grab median {median(paint):.2f} ms; zero render SQL")
    db.close()


if __name__=="__main__": main()
