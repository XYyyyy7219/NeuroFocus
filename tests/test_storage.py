import csv
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from neurofocus.config import Settings,load,save
from neurofocus.engine import Entry
from neurofocus.controller import Controller
from neurofocus.storage import Store,buckets,day_at


class FakeClock:
    def __init__(self):
        self.now=0
        self.wall=round(datetime(2026,3,12,14).timestamp()*1000)
        self.woke=False
    def sample(self):
        woke,self.woke=self.woke,False
        return self.now,self.wall,woke
    def step(self,ms):
        self.now+=ms
        self.wall+=ms


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.path=self.root/"settings.json"
        self.dbpath=self.root/"study.sqlite3"
        self.store=Store(self.dbpath)
        self.addCleanup(self.store.db.close)
        self.clock=FakeClock()
        self.c=Controller(self.store,self.path,Settings(focus=2,low=1,high=1,long=1),self.clock)

    def test_config_roundtrip(self):
        self.c.configure(dark=True,micro=16,voice="柔钟",volume=0)
        self.assertEqual(load(self.path),self.c.settings)

    def test_invalid_settings_preserve_previous(self):
        self.c.configure(focus=3)
        with self.assertRaises(ValueError): self.c.configure(low=20)
        self.assertEqual(load(self.path).low,1)
        with self.assertRaises(ValueError): self.c.configure(micro_on=1)

    def test_failed_atomic_replace_keeps_config(self):
        save(self.path,Settings())
        with patch("neurofocus.config.os.replace",side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.c.configure(dark=True)
        self.assertEqual(load(self.path),Settings())

    def test_changes_apply_next_round(self):
        self.c.start()
        self.c.configure(focus=5)
        self.assertEqual(self.c.engine.target,120000)
        self.c.update("reset")
        self.c.start()
        self.assertEqual(self.c.engine.target,300000)

    def test_suspend_resume_excludes_sleep(self):
        self.c.start()
        self.clock.step(3555)
        self.c.update("suspend")
        self.clock.wall+=36000000
        self.clock.woke=True
        self.c.update()
        self.assertTrue(self.c.engine.paused)
        self.clock.step(19000)
        self.c.update("resume")
        self.clock.step(4445)
        self.c.update("ended")
        self.assertEqual(self.store.history()[0][2],8000)

    def test_missed_suspend_broadcast_pauses_conservatively(self):
        self.c.start()
        self.clock.step(980)
        self.c.update()
        self.clock.wall+=3600000
        self.clock.step(20)
        self.clock.woke=True
        self.c.update()
        self.assertTrue(self.c.engine.paused)
        self.assertEqual(self.c.engine.used,980)

    def test_midnight_attribution(self):
        start=round(datetime(2026,12,31,23,59,59).timestamp()*1000)
        rows=buckets([Entry("micro_start",start),Entry("micro",start,3000),Entry("complete",start+3000)])
        self.assertEqual(rows,{"2026-12-31":[0,1000,0,1,0],"2027-01-01":[0,2000,0,0,1]})

    def test_history_daily_export_no_double_count(self):
        self.c.start()
        for ms in [2400,57600,10000,50000,60000,300000]:
            self.clock.step(ms)
            self.c.update()
        self.assertIsNone(self.c.sid)
        today=day_at(self.clock.wall)
        self.assertEqual(self.store.daily(today,today)[str(today)],(110000,10000,60000,1,1))
        self.assertEqual(self.store.history()[0][1:],("done",110000,10000,60000,1,1))
        path=self.root/"export.csv"
        self.store.export(path)
        with path.open(encoding="utf-8-sig",newline="") as file:
            row=list(csv.DictReader(file))[0]
        self.assertEqual(row["实际专注秒"],"110.0")

    def test_manual_end_after_focus_preserves_completed_cycle(self):
        self.c.start()
        self.clock.step(125000)
        self.c.update("ended")
        self.assertEqual(self.store.history()[0][1:],("ended",110000,10000,5000,1,1))

    def test_checkpoint_failure_rolls_back_and_retries_once(self):
        self.c.start()
        self.store.db.execute("""CREATE TRIGGER fail BEFORE UPDATE ON sessions
            BEGIN SELECT RAISE(ABORT,'failure'); END""")
        self.clock.step(5500)
        with self.assertRaises(sqlite3.IntegrityError): self.c.update("ended")
        self.assertEqual(self.store.history()[0][2],0)
        self.store.db.execute("DROP TRIGGER fail")
        self.c.update()
        self.assertEqual(self.store.history()[0][1:3],("ended",5500))
        self.c.update()
        self.assertEqual(self.store.history()[0][2],5500)

    def test_process_death_inside_transaction(self):
        path=self.root/"crash.sqlite3"
        script="""import os,sys
from neurofocus.storage import Store
from neurofocus.engine import Entry
s=Store(sys.argv[1])
start=1780000000000
i=s.start(start)
s.checkpoint(i,[Entry('focus',start,5000)],start+5000)
s.db.execute('BEGIN')
s.db.execute('UPDATE days SET focus=900000')
os._exit(23)
"""
        child=subprocess.run([sys.executable,"-c",script,str(path)],cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(child.returncode,23)
        for _ in range(2):
            reopened=Store(path)
            self.assertEqual(reopened.db.execute("PRAGMA integrity_check").fetchone(),("ok",))
            self.assertEqual(reopened.history()[0][1:3],("interrupted",5000))
            reopened.db.close()
