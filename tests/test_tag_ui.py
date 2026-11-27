import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

import tempfile
import unittest
from datetime import date
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QLineEdit,QDialogButtonBox
from neurofocus.config import Settings
from neurofocus.controller import Controller
from neurofocus.storage import Store
from neurofocus.window import Window
from neurofocus.tag_ui import TagManager,edit_tag
from test_storage import FakeClock


class TagInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/"test.db")
        self.addCleanup(self.store.db.close)
        self.clock=FakeClock()
        self.c=Controller(self.store,Path(tmp.name)/"config.json",Settings(),self.clock)
        self.window=Window(self.c)
        self.window.timer.stop()
        self.window.show()
        self.addCleanup(self.window.close)
        self.tag=self.store.tags.save("数学","#785624")
        self.window.refresh_tags()

    def test_quick_create_and_switch_without_restarting(self):
        def fill():
            dialog=self.app.activeModalWidget()
            dialog.findChild(QLineEdit).setText("物理")
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
        self.window.primary_action()
        sid=self.c.sid
        self.clock.step(3200)
        QTimer.singleShot(0,fill)
        self.window.pick_tag(self.window.tag_picker.findData("new"))
        self.assertEqual(self.c.sid,sid)
        self.assertEqual(self.window.tag_picker.currentText(),"物理")
        self.clock.step(8200)
        self.c.update("ended")
        rows=self.store.tags.report(date(2026,3,12),date(2026,3,12))[0]
        self.assertEqual([(r[0].name,r[1]) for r in rows],[("物理",8200),("未分类",3200)])

    def test_archiving_current_tag_while_running(self):
        self.window.change_tag(self.tag)
        self.window.primary_action()
        self.clock.step(6400)
        manager=TagManager(self.window)
        manager.act("archive")
        self.assertEqual(self.window.tag_picker.currentData(),0)
        self.clock.step(1600)
        self.c.update("ended")
        self.assertEqual(self.store.tags.history(self.tag,date(2026,1,1),date(2026,12,31),25,0)[0][-1],6400)

    def test_click_slice_opens_detail_and_themes_resize(self):
        self.window.change_tag(self.tag)
        self.window.primary_action()
        self.clock.step(6000)
        self.c.update("ended")
        self.window.navigate(1)
        self.window.stats.tabs.setCurrentIndex(1)
        dist=self.window.stats.distribution
        dist.range.setCurrentText("全部")
        self.window.resize(780,650)
        self.window.configure(dark=True)
        self.app.processEvents()
        ring=dist.ring
        point=QPoint(int(ring.width()/2+ring.radius()),int(ring.height()/2))
        self.assertEqual(ring.hit(point)[0].id,self.tag)
        opened=[]
        def close_detail():
            modal=self.app.activeModalWidget()
            if isinstance(modal,QDialog):
                opened.append(modal.windowTitle())
                modal.accept()
        QTimer.singleShot(0,close_detail)
        QTest.mouseClick(ring,Qt.LeftButton,pos=point)
        self.assertEqual(opened,["数学 · 学习记录"])
        self.assertGreater(dist.table.columnWidth(0),0)
        dist.trend.mode.setCurrentText("周")
        self.assertTrue(dist.trend.plot.bars)
