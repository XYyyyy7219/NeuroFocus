"""Exercise the real application widgets with a simulated clock and a temporary ledger."""
import argparse
from dataclasses import replace
from datetime import datetime,date,time
from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from neurofocus.config import Settings
from neurofocus.controller import Controller
from neurofocus.mode_ui import ModeChooser,ProfileEditor
from neurofocus.storage import Store
from neurofocus.window import Window


class Clock:
    def __init__(self):
        self.now=0
        self.wall=round(datetime.combine(date.today(),time(8)).timestamp()*1000)
    def sample(self): return self.now,self.wall,False
    def step(self,ms):
        self.now+=ms
        self.wall+=ms


def capture(dest):
    app=QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    dest.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        store=Store(root/"study.sqlite3")
        clock=Clock()
        c=Controller(store,root/"settings.json",Settings(audio=False,notify=False),clock)
        w=Window(c)
        w.resize(990,744)
        w.show()
        w.timer.stop()
        def snap(name,widget=None):
            app.processEvents()
            assert (widget or w).grab().save(str(dest/(name+".png")))
        def tick(ms):
            clock.step(ms)
            w.pulse()
        def finish():
            w.advance("ended")
            w.render()
        def start(key):
            dialog=ModeChooser(w)
            dialog.refresh(key)
            dialog.apply()
            w.main_btn.click()
            assert c.engine.config.id==key
        try:
            tag=store.tags.save("理论力学","#718DB2")
            w.change_tag(tag)
            custom=replace(c.profiles.create(),name="推导笔记",focus=45,long=10,grouped=True,short_on=True,rounds=3)
            c.save_profile(custom)
            menu=ModeChooser(w)
            menu.show()
            snap("mode-selector",menu)
            menu.reject()
            start("neuro")
            tick(75000)
            snap("neurofocus")
            finish()
            start("pomo")
            tick(25*60000)
            assert c.engine.phase=="short"
            tick(15000)
            snap("pomodoro-short")
            w.rest_btn.click()
            start("pomo")
            tick(183000)
            snap("pomodoro")
            finish()
            start("deep")
            tick(820000)
            snap("deep-work")
            finish()
            w.configure(dark=True)
            start("flow")
            tick(4213000)
            assert w.dial.state[0]=="1:10:13" and w.dial.state[2] is None
            snap("flowtime")
            c.update("rest",minutes=8)
            tick(30000)
            snap("flowtime-rest")
            w.rest_btn.click()
            w.configure(dark=False)
            editor=ProfileEditor(w,custom)
            editor.show()
            snap("custom-config",editor)
            editor.reject()
            start(custom.id)
            w.resize(760,620)
            tick(200000)
            snap("custom-compact")
            finish()
            w.resize(990,744)
            w.navigate(1)
            w.stats.tabs.setCurrentWidget(w.stats.mode_stats)
            assert w.stats.mode_stats.table.rowCount()==5
            snap("mode-statistics")
            print(f"{app.platformName()} · DPR {w.devicePixelRatioF()} · five policies · ten screenshots")
        finally:
            w.close()
            store.db.close()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    capture(parser.parse_args().output)
