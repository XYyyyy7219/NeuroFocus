from datetime import date,datetime,timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from neurofocus.calendar_data import CalendarData,level,position,records,rolling
from neurofocus.config import Settings,save,load
from neurofocus.engine import Entry
from neurofocus.storage import Store


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.s=Store(":memory:")
        self.addCleanup(self.s.db.close)
        self.a=self.s.tags.save("数学","#009955")
        self.b=self.s.tags.save("英语","#654321")
        self.start=date(2024,2,29)
        self.end=date(2024,3,1)
        w=int(datetime(2024,2,29,23,59,50).timestamp()*1000)
        sid=self.s.start(w)
        self.s.checkpoint(sid,[Entry("focus",w,15000)],w+15000,tag_id=self.a)
        self.s.checkpoint(sid,[Entry("focus",w+15000,20000,1),Entry("micro_start",w+35000),
            Entry("micro",w+35000,1000),Entry("complete",w+36000),Entry("long",w+36000,2500)],
            w+38500,"done",self.b)

    def project(self,keys=None):
        return CalendarData(self.s.db,self.start-timedelta(days=1),self.end+timedelta(days=10),self.end,keys)

    def test_week_positions(self):
        first=date(2023,12,31)
        self.assertEqual(position(first,first),(0,6))
        self.assertEqual(position(first,date(2024,1,1)),(1,0))
        self.assertEqual(position(first,self.start),(9,3))
        self.assertEqual(position(first,self.end),(9,4))
        self.assertEqual(position(date(2012,1,1),date(2012,12,31)),(53,0))

    def test_rolling_window_and_future(self):
        self.assertEqual(rolling(date(2024,2,29),12),(date(2023,3,1),date(2024,2,29)))
        d=CalendarData(self.s.db,self.end,self.end+timedelta(days=30),self.start)
        self.assertEqual((d.ms,d.elapsed,d.active,d.daily_mean,d.active_mean),(0,0,0,0,0))
        self.assertEqual(self.project(set()).days,{})

    def test_thresholds_and_settings(self):
        cuts=(30,90,180)
        self.assertEqual([level(v,cuts) for v in [0,1,1800000,1800001,5400000,5400001,10800000,10800001]],
                         [0,1,1,2,2,3,3,4])
        with self.assertRaises(ValueError): Settings(calendar_low=90)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"prefs.json"
            save(path,Settings(calendar_mid=110))
            self.assertEqual(load(path).calendar_mid,110)

    def test_multi_subject_cycle_cross_midnight_means(self):
        d=self.project({self.a,self.b})
        self.assertEqual((d.ms,d.active,d.elapsed,d.completed),(35000,2,3,1))
        self.assertEqual(d.active_mean,17500)
        self.assertEqual(d.daily_mean,35000/3)
        self.assertEqual(d.days[self.start].ms,10000)
        self.assertEqual((d.days[self.end].cycles,d.days[self.end].micro,d.days[self.end].short_ms,
                          d.days[self.end].long_ms),(1,1,1000,2500))
        self.assertEqual(d.ms,self.s.tags.report(self.start,self.end)[2])
        self.assertEqual(self.project({self.a}).ms,15000)
        self.assertEqual(self.project({self.b}).days[self.end].ms,20000)
        self.assertEqual(self.project({0}).ms,0)

    def test_rest_only_day_and_archived_tag(self):
        self.s.tags.save("语言","#111111",self.b)
        self.s.tags.archive(self.b,True)
        self.assertEqual(self.project({self.b}).tags[self.b],20000)
        day=CalendarData(self.s.db,self.start,self.start,self.end,{self.b}).days[self.start]
        self.assertEqual((day.ms,day.cycles),(0,1))
        self.assertEqual(len(records(self.s.db,self.end,{self.b})),1)

    def test_legacy_null_time_and_partial_session(self):
        self.s.db.execute("INSERT INTO sessions VALUES(88,1,1,'ended')")
        self.s.db.execute("INSERT INTO days VALUES(88,'2024-03-01',1234,0,0,0,0)")
        self.s.db.execute("INSERT INTO focus_spans VALUES(88,'2024-03-01',-1,0,NULL,NULL,1234)")
        self.assertEqual(self.project({0}).ms,1234)
        self.assertEqual(records(self.s.db,self.end,{0})[0][2:4],(None,None))
        self.assertEqual(self.project({0}).completed,0)

    def test_large_history_query_count(self):
        db=self.s.db
        with db:
            db.executemany("INSERT INTO focus_spans VALUES(1,'2024-03-01',?,?,0,1,1)",
                           ((n,self.a) for n in range(10,50010)))
        calls=[]
        db.set_trace_callback(calls.append)
        result=self.project({self.a})
        self.assertEqual(result.ms,65000)
        self.assertEqual(len(calls),2)


class CalendarInteractionTests(unittest.TestCase):
    def test_navigation_selection_refresh_and_repaint_without_queries(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from neurofocus.window import Window
        from neurofocus.controller import Controller
        from test_storage import FakeClock
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(":memory:")
            clock=FakeClock()
            today=date.today()
            clock.wall=int(datetime.combine(today,datetime.min.time()).timestamp()*1000)+3600000
            ctrl=Controller(store,Path(tmp)/"settings.json",Settings(),clock)
            w=Window(ctrl)
            try:
                w.show()
                w.navigate(1)
                cal=w.stats.calendar
                w.stats.tabs.setCurrentWidget(cal)
                self.assertEqual(cal.data.ms,0)
                ctrl.start()
                clock.step(6000)
                w.pulse()
                self.assertEqual(cal.data.ms,6000)
                cal.mode.setCurrentIndex(3)
                cal.year.setValue(2024)
                d=date(2024,2,29)
                QTest.mouseClick(cal.grid,Qt.LeftButton,pos=cal.grid.rect_for(d).center().toPoint())
                self.assertEqual(cal.selected,d)
                cal.next_day.click()
                self.assertEqual(cal.selected,date(2024,3,1))
                cal.today()
                app.processEvents()
                calls=[]
                store.db.set_trace_callback(calls.append)
                self.assertFalse(cal.grid.grab().isNull())
                self.assertEqual(calls,[])
            finally:
                w.close()
                store.db.close()
