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

    def test_surface_lod_and_palette_cache(self):
        from neurofocus.stellar import level,relief,surface
        self.assertEqual([level(r) for r in (0,3.99,4,23.99,24)], [0,0,1,1,2])
        self.assertEqual(level(2,observing=True),3)
        index=relief()
        values={index.pixelIndex(x,y) for x in range(190,450,5) for y in range(190,450,5)}
        self.assertGreater(len(values),40)
        blue=surface("#75c1db").toImage()
        amber=surface("#dfac69").toImage()
        self.assertNotEqual(blue.pixelColor(321,335),amber.pixelColor(321,335))
        self.assertEqual(amber.pixelColor(0,0).alpha(),0)
        self.assertEqual(surface.cache_info().maxsize,12)

    def test_group_preview_matches_real_child_positions(self):
        from neurofocus.stellar import CHILD_SCALE
        self.add(8)
        self.sky.set_low(True)
        overview=[pt for pt,r in self.sky.nodes[(0,)].points]
        self.sky.enter((0,))
        topic=self.sky.nodes[(0,"")]
        self.assertEqual(overview,[(topic.pos()+pt)*CHILD_SCALE for pt,r in topic.points])
        positions=[pt for pt,r in topic.points]
        self.sky.enter((0,""))
        self.assertEqual(positions,[node.pos()*CHILD_SCALE for node in self.sky.nodes.values()])
        self.sky.populate([self.sky.rows[-1]],self.sky.tags,self.sky.slots)
        self.sky.enter(())
        group=self.sky.nodes[(0,)]
        self.assertEqual(group.count,1)
        self.assertEqual(group.anchor,overview[-1])

    def test_observation_restores_camera_and_follows_edited_topic(self):
        self.add(4)
        self.sky.set_low(True)
        self.sky.enter((0,""))
        self.sky.focus_camera(QPointF(22,31),1.3,False)
        center,scale=self.sky.current_pose()
        path=next(iter(self.sky.nodes))
        self.sky.enter(path)
        self.assertTrue(self.stage.panel.isVisible())
        self.assertEqual(self.sky.observing,path[-1])
        self.assertGreater(self.sky.transform().m11(),scale)
        self.sky.ascend()
        actual,zoom=self.sky.current_pose()
        self.assertAlmostEqual(zoom,scale)
        self.assertLess((actual-center).manhattanLength(),3)
        self.sky.enter(path)
        save_note(self.store.db,path[-1],("新章节","<test>","","",""))
        self.h.refresh()
        self.assertEqual(self.sky.scope,(0,"新章节"))
        self.assertEqual(self.sky.observing,path[-1])
        self.assertIn("<test>",self.stage.note.toPlainText())
        self.stage.search.setText("没有这条记录")
        self.stage.apply_search()
        self.assertIsNone(self.sky.observing)
        self.assertFalse(self.stage.panel.isVisible())

    def test_screen_labels_and_clean_mode(self):
        from neurofocus.stellar import label_rect
        from PySide6.QtCore import QRectF
        self.add(5)
        self.sky.set_low(True)
        for scale in (.65,2.4):
            self.sky.focus_camera(QPointF(),scale,False)
            self.sky.viewport().grab()
            self.assertTrue(self.sky.labels)
            _,rect,anchor=self.sky.labels[0]
            self.assertEqual(rect.height(),20)
            self.assertLess((rect.center()-anchor).manhattanLength(),120)
            self.assertFalse(any(rect.intersects(other) for other in self.stage.obstacles()))
        self.assertIsNone(label_rect(QPointF(30,30),(32,20),QRectF(0,0,60,60),[QRectF(0,0,60,60)],5))
        self.stage.toggle_clean()
        self.sky.viewport().grab()
        self.assertEqual(self.sky.labels,[])
        self.assertFalse(self.stage.top.isVisible())
        self.stage.escape()
        self.assertTrue(self.stage.top.isVisible())
