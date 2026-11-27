"""Reproducible local benchmark: python tests/bench_calendar.py from the repo."""
import os
from pathlib import Path
import sys
from datetime import date,timedelta
from statistics import median
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication
from neurofocus.calendar_data import CalendarData
from neurofocus.calendar_ui import Heatmap
from neurofocus.storage import Store


def main():
    app=QApplication([])
    store=Store(":memory:")
    sid=store.start(1700000000000)
    first=date(2024,1,1)
    last=first+timedelta(days=365)
    dates=[(first+timedelta(days=n)).isoformat() for n in range(366)]
    with store.db:
        store.db.executemany("INSERT INTO focus_spans VALUES(?,?,?,0,0,1000,1000)",
                             ((sid,dates[n%366],n) for n in range(50000)))
        store.db.execute("""INSERT INTO days SELECT sid,day,sum(ms),0,0,0,0
                            FROM focus_spans GROUP BY sid,day""")
    grid=Heatmap()
    grid.resize(900,167)
    grid.first,grid.last,grid.today=first,last,last
    grid.show()
    app.processEvents()
    query,paint=[],[]
    for _ in range(11):
        start=perf_counter()
        data=CalendarData(store.db,first,last,last,{0})
        query.append(1000*(perf_counter()-start))
        assert data.ms==50000000 and data.active==366
        grid.days=data.days
        calls=[]
        store.db.set_trace_callback(calls.append)
        start=perf_counter()
        assert not grid.grab().isNull()
        paint.append(1000*(perf_counter()-start))
        assert not calls
        store.db.set_trace_callback(None)
    print(f"50000 spans / 366 dates / 11 rounds: median query {median(query):.2f} ms, "
          f"median 900x167 Qt grab {median(paint):.2f} ms; 0 paint queries.")
    store.db.close()


if __name__=="__main__": main()
