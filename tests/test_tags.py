import csv
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date,datetime
from pathlib import Path

from neurofocus.config import Settings
from neurofocus.controller import Controller
from neurofocus.engine import Entry
from neurofocus.storage import Store
from neurofocus.tags import grouped_days
from test_storage import FakeClock


class TagTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.path=self.root/"test.db"
        self.store=Store(self.path)
        self.addCleanup(self.store.db.close)
        self.tags=self.store.tags
        self.a=self.tags.save("数学","#276B51")
        self.b=self.tags.save("物理","#C87936")
        self.clock=FakeClock()
        self.c=Controller(self.store,self.root/"settings.json",Settings(focus=2,long=1,low=1,high=1),self.clock)
        self.day=date(2026,3,12)

    def study(self,ms,action=None):
        self.clock.step(ms)
        self.c.update(action)

    def rows(self):
        return self.tags.report(self.day,self.day)[0]

    def test_switch_pause_micro_long_and_early_end(self):
        self.c.select_tag(self.a)
        self.c.start()
        self.study(10000,"pause")
        self.clock.step(6000)
        self.c.select_tag(self.b)
        self.study(5000,"resume")
        self.study(50000) # enters micro rest
        self.clock.step(4000)
        self.c.select_tag(self.a)
        self.study(6000) # back to focus
        self.study(55000) # first 50s focus, then long rest
        self.c.select_tag(0)
        self.study(3000,"ended")
        self.assertEqual([(r[0].id,r[1]) for r in self.rows()],[(self.a,60000),(self.b,50000)])
        self.assertEqual(self.store.history()[0][2:5],(110000,10000,8000))
        self.assertEqual(self.tags.history(self.a,self.day,self.day,10,0)[0][-1],50000)

    def test_midnight_half_open_and_returns_to_prior_label(self):
        self.clock.wall=int(datetime(2026,12,31,23,59,58).timestamp()*1000)
        self.c.start()
        self.clock.step(500)
        self.c.select_tag(self.a)
        self.study(2500)
        self.c.select_tag(0)
        self.study(500,"ended")
        _,daily,total=self.tags.report(date(2026,12,31),date(2027,1,1))
        self.assertEqual(daily,[("2026-12-31",0,500),("2026-12-31",self.a,1500),
                                ("2027-01-01",0,500),("2027-01-01",self.a,1000)])
        self.assertEqual(total,3500)

    def test_edit_archive_sort_remember_and_history(self):
        self.c.select_tag(self.a)
        self.c.start()
        self.study(1200,"ended")
        self.tags.save("理论力学","#1100ff",self.a)
        self.tags.move(self.b,-1)
        self.assertEqual([t.id for t in self.tags.all()],[0,self.b,self.a])
        self.assertEqual(self.tags.selected(),self.a)
        self.tags.archive(self.a,True)
        self.assertEqual(self.tags.selected(),0)
        with self.assertRaises(ValueError): self.tags.select(self.a)
        self.assertEqual(self.rows()[0][0].name,"理论力学")
        self.assertTrue(self.rows()[0][0].archived)
        self.assertEqual(self.rows()[0][1],1200)
        self.tags.archive(self.a,False)
        self.tags.select(self.a)
        reopened=Store(self.path)
        self.assertEqual(reopened.tags.selected(),self.a)
        reopened.db.close()

    def test_percent_average_empty_days_and_calendar(self):
        self.c.start()
        self.clock.step(3000)
        self.c.select_tag(self.a)
        self.study(1000,"ended")
        begin,end=self.tags.bounds("自定义",self.day,(date(2026,3,11),self.day))
        rows,daily,total=self.tags.report(begin,end)
        self.assertEqual(total,4000)
        self.assertEqual([(r[2],r[3]) for r in rows],[(.75,1500),(.25,500)])
        for mode,start in [("今日",self.day),("本周",date(2026,3,9)),("本月",date(2026,3,1)),
                           ("本年",date(2026,1,1)),("全部",self.day)]:
            self.assertEqual(self.tags.bounds(mode,self.day),(start,self.day))
        self.assertEqual(grouped_days(daily,"周"),[(date(2026,3,9),{0:3000,self.a:1000})])
        self.assertEqual(grouped_days(daily,"月")[0][0],date(2026,3,1))
        self.assertEqual(self.tags.report(begin,begin),([],[],0))

    def test_failed_switch_retry_retains_original_owner(self):
        self.c.select_tag(self.a)
        self.c.start()
        self.clock.step(3950)
        db=self.store.db
        db.execute("CREATE TRIGGER fail BEFORE UPDATE ON sessions BEGIN SELECT RAISE(ABORT,'fail'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.c.select_tag(self.b)
        self.assertEqual(self.rows(),[])
        self.assertEqual(self.c.tag_id,self.a)
        db.execute("DROP TRIGGER fail")
        self.c.select_tag(self.b)
        self.study(50,"ended")
        self.assertEqual([(r[0].id,r[1]) for r in self.rows()],[(self.a,3950),(self.b,50)])

    def test_checkpoint_compaction_and_pause_creates_two_spans(self):
        self.c.start()
        for _ in range(10): self.study(501)
        self.c.update("pause")
        self.study(6000,"resume")
        self.study(990,"reset")
        lengths=[r[-1] for r in self.tags.history(0,self.day,self.day,25,0)]
        self.assertEqual(lengths,[990,5010])

    def test_csv_json_keep_one_copy_of_rest(self):
        self.c.start()
        self.clock.step(9000)
        self.c.select_tag(self.b)
        self.study(121000,"ended")
        csv_path,json_path=self.root/"x.csv",self.root/"x.json"
        self.store.export(csv_path)
        self.store.export(json_path)
        with csv_path.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual({r["标签名称"] for r in rows},{"未分类","物理"})
        for metric,total in [("实际专注秒",110),("微休息秒",10),("长休息秒",10),("完成周期数",1)]:
            self.assertEqual(sum(float(r[metric]) for r in rows),total)
        payload=json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(sum(s["ms"] for s in payload["focus_spans"]),110000)
        self.assertEqual(sum(r["实际专注秒"] for r in payload["records"]),110)

    def test_old_database_migrates_once_without_inventing_times(self):
        path=self.root/"legacy.db"
        db=sqlite3.connect(path)
        db.executescript("""CREATE TABLE sessions(id INTEGER PRIMARY KEY, started INTEGER,updated INTEGER,status TEXT);
            CREATE TABLE days(sid INTEGER,day TEXT,focus INTEGER,micro INTEGER,long INTEGER,
                micro_count INTEGER,completed INTEGER,PRIMARY KEY(sid,day));
            INSERT INTO sessions VALUES(1,1,9001,'ended');
            INSERT INTO days VALUES(1,'2026-03-12',7000,2000,0,1,0);""")
        db.close()
        for _ in range(2):
            s=Store(path)
            self.assertEqual(s.tags.history(0,self.day,self.day,25,0),[("2026-03-12",1,None,None,7000)])
            self.assertEqual(s.daily(self.day,self.day)[str(self.day)],(7000,2000,0,1,0))
            self.assertEqual(s.db.execute("PRAGMA foreign_key_check").fetchall(),[])
            s.db.close()

    def test_crash_during_tagged_transaction(self):
        path=self.root/"crash.db"
        script="""import os,sys
from neurofocus.storage import Store
from neurofocus.engine import Entry
s=Store(sys.argv[1])
t=s.tags.save('A','#010203')
w=1780000000000
i=s.start(w)
s.checkpoint(i,[Entry('focus',w,1234)],w+1234,tag_id=t)
s.db.create_function('crash',0,lambda: os._exit(23))
s.db.execute('CREATE TRIGGER halt BEFORE UPDATE ON sessions BEGIN SELECT crash(); END')
s.checkpoint(i,[Entry('focus',w+1234,4567)],w+5801,tag_id=t)
"""
        child=subprocess.run([sys.executable,"-c",script,str(path)],cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(child.returncode,23)
        db=sqlite3.connect(path)
        db.execute("DROP TRIGGER halt")
        db.close()
        s=Store(path)
        self.assertEqual(s.history()[0][1:3],("interrupted",1234))
        self.assertEqual(s.db.execute("SELECT tag,ms FROM focus_spans").fetchall(),[(1,1234)])
        self.assertEqual(s.db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        s.db.close()
