import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from neurofocus.config import load,Settings
from neurofocus.controller import Controller
from neurofocus.literature import Library
from neurofocus.reading_ui import Collection
from neurofocus.storage import Store
from neurofocus.window import Window
from test_storage import FakeClock


class ReadingInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        store=Store(self.root/"study.db")
        self.addCleanup(store.db.close)
        self.clock=FakeClock()
        self.w=Window(Controller(store,self.root/"settings.json",Settings(),self.clock))
        self.addCleanup(self.w.close)
        self.w.show()
        self.app.processEvents()

    def test_shows_authorized_local_import_and_pins_during_focus(self):
        w=self.w
        rows=[{**asdict(e),"enabled":False} for e in w.library.entries.values()]
        row={"id":"TEST-MINE","title":"本地创作","text":"校验用的原创小段落。","category":"宁静与自然",
             "scenes":["home","focus","starMap"],"source":{"author":"测试作者","book":"手记"}}
        w.library.import_bundle({"version":1,"entries":[*rows,row]})
        w.reading_refresh(force=True)
        self.assertEqual(w.home_passage.words.full,row["text"])
        w.primary_action()
        w.primary_action()
        self.assertTrue(w.ctrl.engine.paused)
        w.navigate(2)
        w.navigate(0)
        w.primary_action()
        self.clock.step(5000)
        with patch.object(w.library,"choose",side_effect=AssertionError("timer tick reread")):
            w.pulse()
        self.assertEqual(w.home_passage.entry.id,row["id"])
        self.assertEqual(w.ctrl.engine.used,5000)
        w.library.edit(row["id"],enabled=False)
        w.reading_refresh(force=True)
        self.assertTrue(w.home_passage.isHidden())
        w.advance("ended")
        w.render()
        self.assertTrue(w.home_passage.isHidden())

    def test_management_search_flags_and_preferences(self):
        w=self.w
        dialog=Collection(w)
        dialog.search.setText("蛮荒 温柔 少年与理想")
        self.assertEqual(dialog.list.count(),1)
        self.assertEqual(dialog.current().id,"NF-V01-008")
        self.assertFalse(dialog.enabled.isEnabled())
        dialog.favorite.click()
        self.assertTrue(Library(w.library.path).entries["NF-V01-008"].favorite)
        dialog.close()
        w.configure(literary=False,literary_focus=False,literary_frequency="仅手动更换")
        self.assertTrue(w.home_passage.isHidden())
        cfg=load(w.ctrl.path)
        self.assertFalse(cfg.literary)
        self.assertFalse(cfg.literary_focus)
        self.assertEqual(cfg.literary_frequency,"仅手动更换")

    def test_theme_small_window_long_preview_and_sky_hud(self):
        w=self.w
        for dark in (False,True):
            w.configure(dark=dark)
            for width,height in ((760,620),(1120,768)):
                w.resize(width,height)
                self.app.processEvents()
                passage=w.home_passage
                passage.words.display("这是较长的本地测试文字。" * 60)
                self.app.processEvents()
                self.assertLessEqual(len(passage.words.text().splitlines()),2)
                self.assertIn("…",passage.words.text())
                self.assertGreaterEqual(w.dial.height(),200)
                self.assertTrue(w.rect().contains(w.main_btn.mapTo(w,w.main_btn.rect().center())))
        w.navigate(3)
        w.archive.tabs.setCurrentIndex(2)
        self.app.processEvents()
        stage=w.archive.stage
        self.assertTrue(stage.passage.isVisible())
        self.assertIn("starMap",stage.passage.entry.scenes)
        self.assertFalse(stage.passage.geometry().intersects(stage.search.geometry()))
        stage.toggle_clean()
        self.assertFalse(stage.passage.isVisible())
        stage.escape()
        self.assertTrue(stage.passage.isVisible())
