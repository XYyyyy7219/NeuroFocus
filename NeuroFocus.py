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
                    assert w.home_passage.isVisible() and w.home_passage.entry.text
                    assert w.home_passage.entry.source.author=="NeuroFocus"
                    assert sum(e.reviewed and e.text is None for e in w.library.entries.values())==28
                    assert w.grab().save(str(qa/"reading-home-light.png"))
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
                    assert w.home_passage.isVisible() and w.ctrl.sid is not None
                    assert w.grab().save(str(qa/"reading-focus-dark.png"))
                    w.grab().save(str(qa/"windows-dark.png"))
                    w.navigate(2)
                    w.prefs.fields["volume"].setValue(37)
                    assert load(path).volume==37
                    w.advance("ended")
                    w.navigate(1)
                    assert w.stats.table.rowCount()==1
                    store.export(qa/"smoke.csv")
                    # Only the isolated smoke-test database receives these example spans.
                    from time import time_ns
                    from neurofocus.engine import Entry
                    wall=time_ns()//1_000_000
                    tag_a=store.tags.save("数学","#467D68")
                    tag_b=store.tags.save("英语","#BA8056")
                    sid=store.start(wall-600000)
                    store.checkpoint(sid,[Entry("focus",wall-600000,420000)],wall-180000,tag_id=tag_a)
                    store.checkpoint(sid,[Entry("focus",wall-180000,180000,1)],wall,"ended",tag_b)
                    w.refresh_tags()
                    w.tag_picker.activated.emit(w.tag_picker.findData(tag_b))
                    assert controller.tag_id==tag_b
                    w.stats.tabs.setCurrentIndex(1)
                    dist=w.stats.distribution
                    dist.range.setCurrentText("全部")
                    assert dist.ring.total>=600000 and dist.table.rowCount()>=2
                    assert any(tag.id==tag_a and ms==420000 for tag,ms,_,__ in dist.ring.rows)
                    w.grab().save(str(qa/"tags-dark.png"))
                    w.configure(dark=False)
                    w.resize(780,660)
                    app.processEvents()
                    w.grab().save(str(qa/"tags-light.png"))
                    dist.trend.mode.setCurrentText("月")
                    store.export(qa/"tags.json")
                    exported=json.loads((qa/"tags.json").read_text(encoding="utf-8"))
                    assert sum(x["ms"] for x in exported["focus_spans"])==dist.ring.total
                    w.stats.tabs.setCurrentWidget(w.stats.calendar)
                    cal=w.stats.calendar
                    assert cal.data.ms>=600000
                    cal.filter={tag_a}
                    cal.refresh()
                    assert cal.data.ms==420000
                    cal.filter=None
                    cal.refresh()
                    w.resize(1000,820)
                    app.processEvents()
                    w.grab().save(str(qa/"calendar-light.png"))
                    w.configure(dark=True)
                    app.processEvents()
                    w.grab().save(str(qa/"calendar-dark.png"))
                    from datetime import datetime,date,timedelta
                    from neurofocus.history import activities,save_note
                    h=w.archive
                    for i in range(16):
                        d=date.today()-timedelta(days=i//4)
                        at=int(datetime(d.year,d.month,d.day,8+(i%4)*2).timestamp()*1000)
                        span=(22+i)*60000
                        key=store.start(at)
                        store.checkpoint(key,[Entry("focus",at,span)],at+span,"ended",tag_a)
                        a=activities(store.db,key)[0]
                        if i%3:
                            save_note(store.db,a.key,("特征值与特征向量","用一个二阶矩阵验证了推导。","","从例题三继续","良好"))
                    h.open_day(date.today())
                    w.configure(dark=False)
                    app.processEvents()
                    assert h.timeline.rows
                    w.grab().save(str(qa/"learning-timeline.png"))
                    h.tabs.setCurrentIndex(1)
                    h.query.setText("二阶")
                    assert h.model.rowCount()==10
                    app.processEvents()
                    w.grab().save(str(qa/"learning-journal.png"))
                    h.jump_sky()
                    app.processEvents()
                    assert len(h.sky.nodes)==10
                    from neurofocus.starlight import texture
                    assert not texture("deep-field.jpg").isNull() and not texture("spiral.png").isNull()
                    assert h.stage.isVisible() and h.stage.detail_key==h.current
                    h.sky.set_low(True)
                    from neurofocus.stellar import relief
                    assert not relief().isNull()
                    a=h.items[h.current]
                    h.sky.enter((a.tag,a.note[0].strip(),a.key))
                    app.processEvents()
                    assert h.sky.observing==a.key and h.stage.panel.isVisible()
                    assert w.grab().save(str(qa/"stellar-observation.png"))
                    h.sky.ascend()
                    assert h.sky.observing is None
                    h.sky.enter(())
                    app.processEvents()
                    assert h.sky.size()==w.centralWidget().size()
                    assert h.stage.passage.isVisible() and "starMap" in h.stage.passage.entry.scenes
                    assert w.grab().save(str(qa/"reading-sky.png"))
                    from neurofocus.reading_ui import Collection
                    collection=Collection(w)
                    collection.search.setText("夕阳与北辰")
                    collection.show()
                    app.processEvents()
                    assert collection.current().id=="NF-V01-010" and not collection.enabled.isEnabled()
                    assert collection.grab().save(str(qa/"reading-library.png"))
                    collection.close()
                    w.grab().save(str(qa/"learning-universe.png"))
                    assert h.sky.export(str(qa/"universe-export.png"))
                    report=dict(success=True,platform=app.platformName(),
                                calendar=True,archive=True,immersive_sky=True,deep_sky=True,literature=True,
                                frozen=getattr(sys,"frozen",False),history_rows=1,tag_distribution=True,
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
