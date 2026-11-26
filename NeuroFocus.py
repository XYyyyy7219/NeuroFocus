import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from neurofocus.clock import WindowsClock
from neurofocus.config import load
from neurofocus.controller import Controller
from neurofocus.storage import Store
from neurofocus.window import Window


def run():
    smoke = len(sys.argv)==3 and sys.argv[1]=="--smoke-test"
    qa = Path(sys.argv[2]).resolve() if smoke else None
    temp = tempfile.TemporaryDirectory() if smoke else None
    program_dir = Path(sys.executable if getattr(sys,"frozen",False) else __file__).resolve().parent
    data = Path(temp.name) if smoke else program_dir / "data"
    app=QApplication([sys.argv[0]])
    app.setApplicationName("NeuroFocus")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    try:
        data.mkdir(parents=True,exist_ok=True)
        lock=QLockFile(str(data/"instance.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            QMessageBox.information(None,"NeuroFocus","程序已在运行，可从系统托盘打开主窗口。")
            return 0
        path=data/"settings.json"
        try:
            settings=load(path)
        except (ValueError,TypeError,AttributeError):
            from neurofocus.config import Settings
            from time import time_ns
            backup=data/f"settings-invalid-{time_ns()}.json"
            path.rename(backup)
            settings=Settings()
            QMessageBox.information(None,"设置已恢复","原设置文件无法读取，已保留备份并恢复默认值。")
        store=Store(data/"study.sqlite3")
        controller=Controller(store,path,settings,WindowsClock())
        w=Window(controller)
        w.show()
        if smoke:
            qa.mkdir(parents=True,exist_ok=True)
            def verify():
                try:
                    app.processEvents()
                    assert w.isVisible()
                    w.grab().save(str(qa/"windows-light.png"))
                    w.main_btn.click()
                    assert controller.engine.phase=="focus"
                    w.main_btn.click()
                    assert controller.engine.paused
                    w.main_btn.click()
                    assert not controller.engine.paused
                    w.mini_btn.click()
                    assert w.mini.isVisible() and not w.isVisible()
                    w.restore()
                    if w.tray.isSystemTrayAvailable():
                        w.showMinimized()
                        app.processEvents()
                        app.processEvents()
                        assert not w.isVisible()
                        assert controller.engine.phase=="focus" and not controller.engine.paused
                        w.restore()
                    w.configure(dark=True,pinned=True)
                    assert w.pin_btn.isChecked()
                    w.grab().save(str(qa/"windows-dark.png"))
                    w.navigate(2)
                    w.prefs.fields["volume"].setValue(37)
                    assert load(path).volume==37
                    w.advance("ended")
                    w.navigate(1)
                    assert w.stats.table.rowCount()==1
                    store.export(qa/"smoke.csv")
                    report=dict(success=True,platform=app.platformName(),
                                frozen=getattr(sys,"frozen",False),history_rows=1,
                                tray_available=w.tray.isSystemTrayAvailable())
                except Exception:
                    report=dict(success=False,error=traceback.format_exc())
                (qa/"smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
                w.close()
                app.exit(0 if report["success"] else 1)
            QTimer.singleShot(450,verify)
        result=app.exec()
        store.db.close()
        lock.unlock()
        return result
    except Exception:
        error=traceback.format_exc()
        if smoke:
            qa.mkdir(parents=True,exist_ok=True)
            (qa/"smoke.json").write_text(json.dumps(dict(success=False,error=error)),encoding="utf-8")
        else:
            QMessageBox.critical(None,"NeuroFocus 无法启动",error)
        return 1
    finally:
        if temp: temp.cleanup()


if __name__=="__main__":
    sys.exit(run())
