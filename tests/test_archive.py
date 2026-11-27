import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from datetime import date,datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from neurofocus.archive_widgets import JournalEditor
from neurofocus.config import Settings
from neurofocus.controller import Controller
from neurofocus.engine import Entry
from neurofocus.history import activities,markdown,save_note,session_detail
from neurofocus.storage import Store
from neurofocus.universe import layout_slots
from neurofocus.window import Window
from test_storage import FakeClock


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"test.db"
        self.s=Store(self.path)
        self.addCleanup(self.s.db.close)
        self.db=self.s.db
        self.a=self.s.tags.save("数学","#658e84")
        self.b=self.s.tags.save("英语","#e39c72")
        self.clock=FakeClock()
        self.c=Controller(self.s,self.path.with_suffix(".json"),Settings(focus=3,low=1,high=1,micro=10),self.clock)
        self.c.select_tag(self.a)

    def record(self):
        self.c.start()
        self.clock.step(72000)
        self.c.update("pause")
        self.clock.step(3045)
        self.c.update("resume")
        self.clock.step(10000)
        self.c.select_tag(self.b)
        self.clock.step(4567)
        self.c.update("ended")
        return activities(self.db)

    def test_events_pause_config_and_micro_grouping(self):
        rows=self.record()
        self.assertEqual([a.ms for a in rows],[72000,4567])
        self.assertEqual([len(a.spans) for a in rows],[3,1])
        self.assertEqual(self.db.execute("SELECT paused_ms FROM session_protocol").fetchone()[0],3045)
        self.assertEqual([r[0] for r in self.db.execute("SELECT kind FROM study_events ORDER BY id")],
                         ["start","micro_start","resume_focus","pause","resume","tag","ended"])
        self.assertIn("3.045 秒",session_detail(self.db,rows[0]))
        self.assertEqual(sum(a.ms for a in rows),self.s.history()[0][2])

    def test_midnight_activity_keys_and_draft_survive_reopening(self):
        self.clock.wall=int(datetime(2026,12,31,23,59,59).timestamp()*1000)
        self.c.start()
        self.clock.step(5500)
        self.c.update("ended")
        a,b=activities(self.db)
        self.assertEqual([a.ms,b.ms],[1000,4500])
        self.assertEqual(a.key[0],b.key[0])
        save_note(self.db,a.key,("递归","理解函数栈","","p.12","良好"))
        with sqlite3.connect(self.path) as other:
            a2=activities(other)[0]
            self.assertTrue(a2.matches("函数"))
            self.assertIn("p.12",markdown(a2,"数学"))
        other.close()
        self.s.tags.save("理论数学","#112233",self.a)
        self.s.tags.archive(self.a,True)
        self.assertEqual(activities(self.db)[0].key,a.key)
        save_note(self.db,a.key,("",)*5)
        self.assertFalse(any(activities(self.db)[0].note))
        self.assertEqual(activities(self.db)[0].ms,1000)

    def test_migration_backup_is_complete_and_once(self):
        rows=self.record()
        for name in ("journal","session_protocol","study_events"):
            self.db.execute("DROP TABLE "+name)
        self.db.commit()
        for _ in range(2):
            newer=Store(self.path)
            self.assertEqual([r.key for r in activities(newer.db)],[r.key for r in rows])
            self.assertFalse(newer.db.execute("SELECT * FROM study_events").fetchall())
            self.assertEqual(newer.db.execute("PRAGMA foreign_key_check").fetchall(),[])
            newer.db.close()
        backups=list(self.path.parent.glob("study-before-archive-*.sqlite3"))
        self.assertEqual(len(backups),1)
        with sqlite3.connect(backups[0]) as old:
            self.assertEqual(old.execute("SELECT sum(ms) FROM focus_spans").fetchone()[0],76567)
            self.assertIsNone(old.execute("SELECT 1 FROM sqlite_master WHERE name='journal'").fetchone())
        old.close()

    def test_return_to_tag_distinct_and_slots_survive_append(self):
        rows=self.record()
        slots=layout_slots(rows)
        self.c.start()
        self.clock.step(1000)
        self.c.select_tag(self.a)
        self.clock.step(1000)
        self.c.select_tag(self.b)
        self.clock.step(1000)
        self.c.update("ended")
        all_rows=activities(self.db)
        self.assertEqual(len(all_rows),5)
        self.assertEqual(len({a.key for a in all_rows}),5)
        after=layout_slots(all_rows)
        self.assertTrue(all(after[k]==v for k,v in slots.items()))

    def test_calendar_timeline_journal_star_navigation_and_autosave(self):
        app=QApplication.instance() or QApplication([])
        rows=self.record()
        w=Window(self.c)
        self.addCleanup(w.close)
        w.show()
        h=w.archive
        h.open_day(date.fromisoformat(rows[0].day))
        self.assertEqual(len(h.model.rows),2)
        h.select(rows[0].key)
        editor=JournalEditor(w,self.db,rows[0],"数学")
        editor.topic.setText("矩阵")
        editor.gain.setPlainText("理解了特征向量")
        QTest.qWait(575)
        self.assertEqual(activities(self.db)[0].note[0],"矩阵")
        editor.accept()
        h.refresh()
        h.tabs.setCurrentIndex(1)
        h.query.setText("特征")
        self.assertEqual(len(h.model.rows),1)
        h.jump_sky()
        star=h.sky.nodes[(self.a,"矩阵",rows[0].key)]
        self.assertTrue(star.ring)
        self.assertTrue(star.active)
        pos=star.pos()
        h.jump_time()
        self.assertEqual(h.current,rows[0].key)
        h.jump_sky()
        self.assertEqual(h.sky.nodes[(self.a,"矩阵",rows[0].key)].pos(),pos)
        h.range_on.setChecked(True)
        h.first.setDate(date(2030,1,1))
        self.assertEqual(h.model.rowCount(),0)
        w.resize(760,620)
        app.processEvents()
        self.assertFalse(w.grab().isNull())

    def test_checkpoint_retry_does_not_duplicate_events(self):
        self.c.start()
        self.clock.step(65500)
        self.db.execute("""CREATE TRIGGER refuse BEFORE UPDATE ON sessions
            BEGIN SELECT RAISE(ABORT,'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError): self.c.update("ended")
        self.assertEqual(self.db.execute("SELECT count(*) FROM study_events").fetchone()[0],1)
        self.db.execute("DROP TRIGGER refuse")
        self.c.update()
        self.assertEqual([e[0] for e in self.db.execute("SELECT kind FROM study_events ORDER BY id")],
                         ["start","micro_start","ended"])
        self.assertEqual(activities(self.db)[0].ms,60000)

    def test_visible_star_updates_without_replacing_item_and_scrubs_by_day(self):
        app=QApplication.instance() or QApplication([])
        rows=self.record()
        w=Window(self.c)
        self.addCleanup(w.close)
        w.show()
        h=w.archive
        h.open_day(date.fromisoformat(rows[0].day))
        h.select(rows[0].key)
        h.jump_sky()
        path=(self.a,"",rows[0].key)
        node=h.sky.nodes[path]
        save_note(self.db,rows[0].key,("","有新收获","","",""))
        h.refresh()
        self.assertIs(h.sky.nodes[path],node)
        self.assertTrue(node.ring)
        self.clock.step(86400000)
        self.c.start()
        self.clock.step(7000)
        self.c.update("ended")
        h.refresh()
        h.sky.enter(())
        h.slide.setValue(h.slide.maximum())
        self.assertEqual(h.model.rowCount(),3)
        h.slide.setValue(0)
        self.assertEqual(h.model.rowCount(),2)
        self.assertFalse(h.sky.grab().isNull())
