import os,tempfile,unittest
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from PySide6.QtWidgets import QApplication,QMessageBox
from neurofocus.config import Settings
from neurofocus.controller import Controller
from neurofocus.mode_ui import ModeChooser,ProfileEditor
from neurofocus.sound import NOTES
from neurofocus.storage import Store
from neurofocus.window import Window
from test_storage import FakeClock

class ModeInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        store=Store(root/"study.db")
        self.addCleanup(store.db.close)
        self.clock=FakeClock()
        self.c=Controller(store,root/"settings.json",Settings(audio=False,notify=False),self.clock)
        self.w=Window(self.c)
        self.addCleanup(self.w.close)
        self.w.show()
        self.app.processEvents()

    def test_custom_editor_visibility_identity_and_delete(self):
        w=self.w
        p=self.c.profiles.create()
        form=ProfileEditor(w,p)
        form.show()
        self.app.processEvents()
        form.inputs["count_up"].setChecked(True)
        form.inputs["micro_on"].setChecked(False)
        self.assertTrue(form.inputs["focus"].isHidden())
        self.assertTrue(form.inputs["low"].isHidden())
        self.assertTrue(form.inputs["rounds"].isHidden())
        form.inputs["name"].setText("自由写作")
        form.inputs["grouped"].setChecked(True)
        self.assertFalse(form.inputs["rounds"].isHidden())
        form.save()
        self.c.save_profile(form.result_profile)
        chooser=ModeChooser(w)
        chooser.refresh(p.id)
        chooser.apply()
        w.main_btn.click()
        self.assertEqual(w.dial.state[:3],("00:00","专注中",None))
        self.clock.step(3700001)
        w.pulse()
        self.assertEqual(w.mini.time.text(),"1:01:40")
        chooser=ModeChooser(w)
        chooser.refresh(p.id)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.Yes):
            chooser.remove()
        self.assertEqual(self.c.engine.config.id,p.id)
        self.assertEqual(self.c.selected_profile.id,"neuro")
        self.assertIn("下一轮",w.caption.text())
        w.advance("ended")
        chooser.close()

    def test_pomo_manual_rest_button_and_distinct_notifications(self):
        self.c.save_profile(replace(self.c.profiles.items["pomo"],focus=1,auto_long=False))
        self.c.profiles.select("pomo")
        with patch.object(self.w,"play") as sound:
            self.w.main_btn.click()
            self.clock.step(60000)
            self.w.pulse()
            self.assertIn("开始短休息",self.w.main_btn.text())
            self.w.main_btn.click()
            self.w.pulse()
            self.assertEqual(self.c.engine.phase,"short")
            self.clock.step(500)
            self.w.rest_btn.click()
            self.assertEqual(self.c.engine.phase,"idle")
            self.assertEqual([c.args[0] for c in sound.call_args_list],["start","complete","short_start","short_end"])
        self.assertNotEqual(NOTES["short_start"],NOTES["long_start"])

    def test_flowtime_rest_and_mode_stats_range(self):
        self.c.profiles.select("flow")
        self.w.main_btn.click()
        self.clock.step(12346)
        self.w.pulse()
        with patch("neurofocus.window.QInputDialog.getInt",return_value=(8,True)): self.w.rest_btn.click()
        self.assertEqual(self.c.engine.phase,"manual")
        self.w.main_btn.click()
        self.clock.step(400)
        self.w.main_btn.click()
        self.clock.step(100)
        self.w.rest_btn.click()
        self.w.navigate(1)
        panel=self.w.stats.mode_stats
        self.w.stats.tabs.setCurrentWidget(panel)
        panel.range.setCurrentIndex(2)
        self.assertEqual(panel.table.item(0,0).text(),"Flowtime")
        self.assertEqual(panel.table.item(0,3).text(),"1")
        panel.range.setCurrentIndex(3)
        panel.first.setDate(panel.last.date().addDays(2))
        self.assertEqual(panel.table.rowCount(),0)

    def test_archive_linked_flowtime_details_and_event_marker(self):
        self.c.profiles.select("flow")
        self.w.main_btn.click()
        self.clock.step(15000)
        self.c.update("rest",minutes=5)
        self.clock.step(2000)
        self.c.update("skip_rest")
        from datetime import datetime
        d=datetime.fromtimestamp(self.clock.wall/1000).date()
        archive=self.w.archive
        archive.open_day(d)
        a=next(iter(archive.items.values()))
        self.assertEqual(a.mode_name,"Flowtime")
        self.assertEqual(archive.timeline.markers[0][1],"manual_start")
        archive.select(a.key)
        archive.jump_sky()
        self.assertEqual(archive.sky.observing,a.key)
        self.assertIn("Flowtime",archive.stage.note.toPlainText())
        self.assertIn("自主休息",archive.stage.note.toPlainText())
