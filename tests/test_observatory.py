import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,QPointF,Qt,QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from neurofocus.config import Settings,load
from neurofocus.controller import Controller
from neurofocus.history import save_note
from neurofocus.storage import Store
from neurofocus.starlight import texture
from neurofocus.window import Window
from test_storage import FakeClock


class ObservatoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.store=Store(root/"study.db")
        self.addCleanup(self.store.db.close)
        self.cfg=root/"settings.json"
        self.w=Window(Controller(self.store,self.cfg,Settings(),FakeClock()))
        self.addCleanup(self.w.close)
        self.w.show()
        self.w.navigate(3)
        self.h=self.w.archive
        self.h.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.stage=self.h.stage
        self.sky=self.h.sky

    def add(self,n):
        db=self.store.db
        with db:
            for i in range(n):
                sid=i+1
                db.execute("INSERT INTO sessions VALUES(?,0,2000,'ended')",(sid,))
                db.execute("INSERT INTO focus_spans VALUES(?,'2026-03-12',0,0,0,2000,2000)",(sid,))
        self.h.refresh()

    def test_empty_single_and_dense_semantics(self):
        self.assertEqual(len(self.sky.nodes),0)
        self.assertTrue(self.stage.isVisible())
        self.assertFalse(texture("spiral.png").isNull())
        self.add(321)
        group=self.sky.nodes[(0,)]
        self.assertEqual(group.count,321)
        self.assertEqual(len(group.points),160)
        self.assertEqual(len({(round(p.x(),8),round(p.y(),8)) for p,_ in group.points}),160)
        self.sky.enter((0,""))
        self.assertEqual(len(self.sky.nodes),321)
        self.assertEqual(set(k[-1] for k in self.sky.nodes),set(self.h.items))

    def test_fullscreen_and_navigation_restore(self):
        self.stage.fullscreen()
        self.assertTrue(self.w.isFullScreen())
        self.stage.escape()
        self.assertFalse(self.w.isFullScreen())
        self.stage.leave()
        self.assertFalse(self.stage.isVisible())
        self.assertEqual(self.h.tabs.currentIndex(),0)
        self.h.tabs.setCurrentIndex(2)
        self.w.navigate(0)
        self.assertTrue(self.stage.isHidden())
        self.w.navigate(3)
        self.assertTrue(self.stage.isVisible())

    def test_search_focus_and_low_motion_persist(self):
        self.add(3)
        a=list(self.h.items.values())[1]
        save_note(self.store.db,a.key,("光谱","验证例题","","",""))
        self.h.refresh()
        self.stage.low_motion(True)
        self.assertTrue(load(self.cfg).sky_low_motion)
        self.stage.search.setText("验证例题")
        self.stage.apply_search()
        self.assertEqual(self.sky.selected,a.key)
        self.assertEqual(self.h.current,a.key)
        self.assertTrue(self.stage.panel.isVisible())
        self.assertFalse(self.sky._camera.state().value)
        self.stage.toggle_results()
        self.assertTrue(self.stage.matches.isVisible())
        self.h.jump_time()
        self.assertTrue(self.stage.isHidden())
        self.assertEqual(self.h.current,a.key)

    def test_zoom_anchor_and_plain_export(self):
        self.add(5)
        self.sky.set_low(True)
        self.sky.enter((0,""))
        pos=QPoint(250,190)
        before=self.sky.mapToScene(pos)
        e=QWheelEvent(QPointF(pos),QPointF(self.sky.mapToGlobal(pos)),QPoint(),QPoint(0,120),
                      Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        self.sky.wheelEvent(e)
        self.assertLess((self.sky.mapToScene(pos)-before).manhattanLength(),3)
        out=self.cfg.with_suffix(".png")
        self.assertTrue(self.sky.export(str(out)))
        from PySide6.QtGui import QImage
        self.assertEqual(QImage(str(out)).size(),self.sky.viewport().size()*2)
