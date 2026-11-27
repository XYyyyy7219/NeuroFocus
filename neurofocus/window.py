import ctypes
import sqlite3
from ctypes import wintypes
from datetime import date
from PySide6.QtCore import Qt, QEvent, QSize, QTimer
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QFrame,QStackedWidget,
    QMenu,QSystemTrayIcon,QMessageBox,QComboBox)
from .tag_ui import swatch, edit_tag, TagManager
from .visual import LIGHT,DARK,icon,stamp,Dial,Terrain
from .widgets import box,label,button,card,stylesheet
from .pages import Preferences,Statistics,duration
from .storage import buckets
from .sound import Chimes
from .archive_ui import Archive


PHASE={"idle":"待机","focus":"专注中","micro":"微休息","long":"长休息"}
NOTICES={"micro_start":"放松，自然休息","resume_focus":"微休息结束，继续学习",
         "long_start":"专注周期已完成，进入长休息","long_end":"长休息结束，可以开始下一轮",
         "complete":"专注周期已完成","wake_pause":"系统已唤醒，点击继续开始计时"}


class Mini(QWidget):
    def __init__(self,window):
        super().__init__(None,Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.w=window
        self.setObjectName("shell")
        self.setWindowTitle("NeuroFocus · 悬浮小窗")
        self.setFixedSize(165,90)
        col=box(self,margins=8,spacing=0)
        self.phase=label("","cap")
        self.time=label("","title")
        for w in (self.phase,self.time):
            w.setAlignment(Qt.AlignCenter)
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            col.addWidget(w)
        self.setToolTip("拖动移动 · 双击返回主窗口")
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):
        self.w.restore()
    def closeEvent(self,event):
        self.w.restore()
        event.accept()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Escape,Qt.Key_Return):
            self.w.restore()
        else:
            super().keyPressEvent(event)


class Window(QMainWindow):
    def __init__(self,ctrl):
        super().__init__()
        self.ctrl=ctrl
        self.setWindowTitle("NeuroFocus · 专注学习")
        self.setMinimumSize(760,620)
        self.resize(990,744)
        self.audio=Chimes(ctrl.path.parent)
        self.last_message=""
        self.last_stats=None
        self.failing=False
        self.icons=[]
        shell=QWidget()
        shell.setObjectName("shell")
        self.setCentralWidget(shell)
        root=box(shell,True,spacing=0)
        side=QFrame()
        side.setObjectName("side")
        side.setFixedWidth(206)
        root.addWidget(side)
        side_box=box(side,margins=(14,27,14,23),spacing=7)
        brand=box(horizontal=True,margins=(4,0,0,0))
        mark=label("")
        mark.setPixmap(icon("logo","#C1DFB1").pixmap(29,29))
        brand.addWidget(mark)
        brand.addWidget(label("NeuroFocus","brand"))
        brand.addStretch()
        side_box.addLayout(brand)
        side_box.addSpacing(39)
        self.nav=[]
        for i,(title,name) in enumerate([("专注计时","timer"),("学习统计","chart"),("偏好设置","settings"),("学习档案","cycle")]):
            b=button("  "+title,"nav",lambda _,n=i:self.navigate(n))
            b.setIcon(icon(name,"#C4DECA"))
            b.setIconSize(QSize(19,19))
            b.setCheckable(True)
            self.nav.append(b)
            side_box.addWidget(b)
        side_box.addStretch()
        side_box.addWidget(Terrain())
        side_box.addWidget(label("当前计时方案","sidecap"))
        self.protocol=label("","sidevalue")
        self.protocol.setWordWrap(True)
        side_box.addWidget(self.protocol)
        content=box(margins=(26,22,26,22),spacing=12)
        root.addLayout(content,1)
        toolbar=box(horizontal=True)
        heading=box(spacing=2)
        self.dateline=label("","cap")
        self.title=label("专注计时","title")
        heading.addWidget(self.dateline)
        heading.addWidget(self.title)
        toolbar.addLayout(heading)
        toolbar.addStretch()
        self.mini_btn=self.tool("mini","悬浮小窗",self.show_mini)
        self.pin_btn=self.tool("pin","主窗口置顶",lambda:self.configure(pinned=not self.ctrl.settings.pinned))
        self.pin_btn.setCheckable(True)
        self.theme_btn=self.tool("moon","切换深浅模式",lambda:self.configure(dark=not self.ctrl.settings.dark))
        for b in (self.mini_btn,self.pin_btn,self.theme_btn): toolbar.addWidget(b)
        content.addLayout(toolbar)
        self.stack=QStackedWidget()
        content.addWidget(self.stack,1)
        self.make_timer()
        self.stats=Statistics(self)
        self.prefs=Preferences(self)
        self.stack.addWidget(self.stats)
        self.stack.addWidget(self.prefs)
        self.archive=Archive(self)
        self.stack.addWidget(self.archive)
        self.mini=Mini(self)
        self.tray=QSystemTrayIcon(icon("logo","#6CA789"),self)
        self.tray.setToolTip("NeuroFocus")
        menu=QMenu(self)
        menu.addAction("显示主窗口",self.restore)
        self.tray_action=menu.addAction("开始专注",self.primary_action)
        menu.addSeparator()
        menu.addAction("退出 NeuroFocus",self.close)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r:self.restore() if r in (
            QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick) else None)
        self.tray.messageClicked.connect(self.restore)
        self.tray.show()
        self.setWindowIcon(icon("logo","#478266"))
        self.timer=QTimer(self)
        self.timer.timeout.connect(self.pulse)
        self.timer.start(1000)
        self.theme()
        self.setWindowFlag(Qt.WindowStaysOnTopHint,ctrl.settings.pinned)
        self.navigate(0)

    def tool(self,key,title,fn):
        b=button("","tool",fn)
        b.setToolTip(title)
        b.setAccessibleName(title)
        self.icons.append((b,key))
        return b

    def make_timer(self):
        page=QWidget()
        col=box(page,spacing=12)
        hero=card()
        center=box(hero,margins=(20,14,20,16),spacing=3)
        row=box(horizontal=True)
        row.addWidget(label("本轮专注","head"))
        self.tag_picker=QComboBox()
        self.tag_picker.setAccessibleName("当前学习标签")
        self.tag_picker.setToolTip("选择学习标签，可在专注中切换")
        self.tag_picker.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.tag_picker.setMinimumContentsLength(5)
        self.tag_picker.setMaximumWidth(190)
        self.refresh_tags()
        self.tag_picker.activated.connect(self.pick_tag)
        row.addWidget(self.tag_picker)
        self.breakpoint=button("学习断点",handler=self.show_breakpoint)
        row.addWidget(self.breakpoint)
        row.addStretch()
        self.badge=label("","pill")
        row.addWidget(self.badge)
        center.addLayout(row)
        self.dial=Dial()
        center.addWidget(self.dial,1)
        self.caption=label("","muted")
        self.caption.setAlignment(Qt.AlignCenter)
        center.addWidget(self.caption)
        self.journal_link=button("补写本轮日志",handler=self.recent_journal)
        center.addWidget(self.journal_link,0,Qt.AlignCenter)
        self.journal_link.hide()
        center.addSpacing(8)
        controls=box(horizontal=True,spacing=8)
        controls.addStretch()
        self.main_btn=button("开始专注","primary",self.primary_action)
        self.main_btn.setMinimumWidth(148)
        controls.addWidget(self.main_btn)
        self.stop_btn=self.tool("stop","结束本轮",lambda:self.finish("ended"))
        self.reset_btn=self.tool("reset","重置本轮",lambda:self.finish("reset"))
        for b in (self.stop_btn,self.reset_btn):
            controls.addWidget(b)
        controls.addStretch()
        center.addLayout(controls)
        col.addWidget(hero,1)
        row=box(horizontal=True)
        row.addWidget(label("今日概览","head"))
        row.addStretch()
        details=button("查看统计  ›",handler=lambda:self.navigate(1))
        row.addWidget(details)
        col.addLayout(row)
        metrics=box(horizontal=True,spacing=10)
        self.values=[]
        self.metric_icons=[]
        for title,key in [("实际专注","clock"),("完成周期","cycle"),("微休息","leaf")]:
            tile=card()
            column=box(tile,margins=(15,11,12,11),spacing=2)
            row=box(horizontal=True,spacing=6)
            glyph=label("")
            self.metric_icons.append((glyph,key))
            row.addWidget(glyph)
            row.addWidget(label(title,"muted"))
            row.addStretch()
            column.addLayout(row)
            value=label("","metric")
            column.addWidget(value)
            self.values.append(value)
            metrics.addWidget(tile,1)
        col.addLayout(metrics)
        self.stack.addWidget(page)

    def refresh_tags(self):
        picker=self.tag_picker
        picker.clear()
        for tag in self.ctrl.store.tags.all():
            if not tag.archived:
                picker.addItem(swatch(tag.color),tag.name,tag.id)
        picker.insertSeparator(picker.count())
        picker.addItem("＋ 新建学习标签","new")
        picker.addItem("管理标签…","manage")
        picker.setCurrentIndex(picker.findData(self.ctrl.tag_id))

    def change_tag(self,key):
        self.notify_events(self.ctrl.select_tag(key))
        self.refresh_tags()
        self.render()

    def pick_tag(self,index):
        key=self.tag_picker.itemData(index)
        self.refresh_tags()
        try:
            if key=="manage":
                TagManager(self).exec()
            else:
                if key=="new": key=edit_tag(self)
                if key is not None: self.change_tag(key)
        except (ValueError,sqlite3.Error) as exc:
            QMessageBox.warning(self,"无法切换标签",str(exc))
        self.refresh_tags()

    def navigate(self,index):
        self.stack.setCurrentIndex(index)
        self.title.setText(("专注计时","学习统计","偏好设置","学习档案")[index])
        for i,b in enumerate(self.nav): b.setChecked(i==index)
        if index==1:
            self.advance("flush")
            self.stats.refresh()
        elif index==3:
            self.advance("flush")
            self.archive.refresh()
        self.render()

    def show_breakpoint(self):
        row=self.ctrl.store.db.execute("""SELECT day,next_step FROM journal WHERE tag=?
            AND trim(next_step)<>'' ORDER BY day DESC,sid DESC,block DESC LIMIT 1""",(self.ctrl.tag_id,)).fetchone()
        text="该标签还没有学习断点。写日志时可把下次的起点留在「下一步」。"
        if row: text=row[0]+"\n\n"+row[1]
        msg=QMessageBox(self)
        msg.setWindowTitle("学习断点")
        msg.setTextFormat(Qt.PlainText)
        msg.setText(text)
        msg.exec()

    def recent_journal(self):
        self.navigate(3)
        rows=[a for a in self.archive.items.values() if a.key[0]==self.recent_sid]
        if rows:
            a=rows[-1]
            self.archive.open_day(date.fromisoformat(a.day))
            self.archive.select(a.key)
            self.archive.edit()

    def theme(self):
        c=DARK if self.ctrl.settings.dark else LIGHT
        self.dial.colors=c
        app=QApplication.instance()
        pal=app.palette()
        for role,key in [(QPalette.Window,"bg"),(QPalette.WindowText,"ink"),(QPalette.Text,"ink"),
                         (QPalette.ButtonText,"ink"),(QPalette.Base,"card"),(QPalette.Button,"card"),
                         (QPalette.Highlight,"accent"),(QPalette.HighlightedText,"card")]:
            pal.setColor(role,QColor(c[key]))
        app.setPalette(pal)
        app.setStyleSheet(stylesheet(c))
        for w,key in self.icons:
            w.setIcon(icon("sun" if w==self.theme_btn and self.ctrl.settings.dark else key,c["muted"]))
        for w,key in self.metric_icons: w.setPixmap(icon(key,c["accent"]).pixmap(15,15))
        self.pin_btn.setChecked(self.ctrl.settings.pinned)
        self.prefs.sync()
        self.dial.update()
        self.last_button=None

    def configure(self,**changes):
        try:
            self.ctrl.configure(**changes)
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"设置未保存",str(exc))
            self.prefs.sync()
            return
        if "pinned" in changes:
            self.setWindowFlag(Qt.WindowStaysOnTopHint,changes["pinned"])
            self.show()
        if "dark" in changes:
            self.theme()
            if self.stack.currentIndex()==1: self.stats.refresh()
        self.pin_btn.setChecked(self.ctrl.settings.pinned)
        self.prefs.sync()
        self.render()

    def play(self,key):
        try:
            self.audio.play(key,self.ctrl.settings)
        except (OSError,RuntimeError):
            self.last_message="提示音播放失败，请检查系统音频输出"

    def advance(self,action=None):
        sid=self.ctrl.sid
        events=self.ctrl.update(action)
        self.notify_events(events)
        if sid is not None and (self.ctrl.sid is None or "complete" in events):
            self.recent_sid=sid
            self.journal_link.setVisible(bool(self.ctrl.store.db.execute(
                "SELECT 1 FROM focus_spans WHERE sid=? LIMIT 1",(sid,)).fetchone()))

    def notify_events(self,events):
        if events:
            last=events[-1]
            self.last_message=NOTICES[last]
            self.play(last)
            if self.ctrl.settings.notify and self.tray.isSystemTrayAvailable():
                self.tray.showMessage("NeuroFocus",self.last_message,QSystemTrayIcon.Information,4000)

    def pulse(self):
        try:
            self.advance()
            self.render()
        except sqlite3.Error as exc:
            self.db_error(exc)

    def db_error(self,exc):
        self.ctrl.engine.paused=self.ctrl.engine.phase!="idle"
        if self.failing: return
        self.failing=True
        self.timer.stop()
        QMessageBox.warning(self,"学习记录暂未保存",f"计时已暂停。请检查磁盘空间和文件权限，再继续。\n{exc}")
        self.timer.start(1000)
        self.failing=False

    def primary_action(self):
        e=self.ctrl.engine
        try:
            if e.phase=="idle":
                self.ctrl.start()
                self.journal_link.hide()
                self.last_message=""
            else:
                self.advance("resume" if e.paused else "pause")
            self.render()
        except sqlite3.Error as exc:
            self.db_error(exc)

    def finish(self,action):
        title="重置" if action=="reset" else "结束"
        if QMessageBox.question(self,title+"本轮",title+"本轮并返回待机？已经学习的时间会保留。",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        self.advance(action)
        self.last_message="已重置，可开始新一轮" if action=="reset" else "本轮已结束，学习记录已保存"
        self.render()

    def render(self):
        e=self.ctrl.engine
        idle=e.phase=="idle"
        cfg=self.ctrl.settings if idle else e.config
        today=date.today()
        self.dateline.setText(f"{today.year} 年 {today.month:02} 月 {today.day:02} 日   /   星期"+"一二三四五六日"[today.weekday()])
        self.protocol.setText(f"{cfg.focus} 分钟专注   /   {cfg.long} 分钟休息")
        status=("已暂停" if e.paused else PHASE[e.phase])
        title=("准备专注" if idle else PHASE[e.phase]) if not e.paused else PHASE[e.phase]+" · 已暂停"
        time=stamp(cfg.focus*60000 if idle else e.remaining())
        progress=0 if idle else e.used/e.target
        state=(time,title,progress,e.phase)
        if self.dial.state!=state:
            self.dial.state=state
            self.dial.setAccessibleDescription(f"{title} {time}")
            self.dial.update()
        self.badge.setText(status)
        self.mini.phase.setText(title)
        self.mini.time.setText(time)
        if idle:
            note=self.last_message or f"{cfg.focus} 分钟专注   ·   "+("随机微休息" if cfg.micro_on else "连续专注")
        elif e.paused: note="计时已暂停，准备好后继续"
        elif e.phase=="micro": note=f"放松，自然休息   ·   周期进度 {progress:.0%}"
        elif e.phase=="long": note="专注周期已完成，给自己一段休息时间"
        else: note=f"专注周期进度   {progress:.0%}"
        self.caption.setText(note)
        text="开始专注" if idle else "继续" if e.paused else "暂停"
        if self.last_button!=text:
            self.last_button=text
            self.main_btn.setText("  "+text)
            self.main_btn.setIcon(icon("pause" if text=="暂停" else "play",self.dial.colors["card"]))
            self.tray_action.setText(text)
        self.stop_btn.setVisible(not idle)
        self.reset_btn.setVisible(not idle)
        # Skip idle disk reads and avoid redrawing history while navigating it.
        key=(today,self.ctrl.saved,self.ctrl.sid)
        if self.last_stats!=key:
            self.last_stats=key
            self.today_base=self.ctrl.store.daily(today,today).get(str(today),(0,)*5)
            if self.stack.currentIndex()==1: self.stats.refresh()
            if self.stack.currentIndex()==3: self.archive.refresh()
        extra=buckets(self.ctrl.pending).get(str(today),(0,)*5)
        actual,_,__,micro,complete=(a+b for a,b in zip(self.today_base,extra))
        self.values[0].setText(duration(actual))
        self.values[1].setText(f"{complete} 轮")
        self.values[2].setText(f"{micro} 次")
        self.tray.setToolTip(f"NeuroFocus · {title} {time}")
        interval=1000 if idle or e.paused else 250 if self.isVisible() or self.mini.isVisible() else 1000
        if self.timer.interval()!=interval: self.timer.setInterval(interval)

    def restore(self):
        self.mini.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_mini(self):
        if not self.mini.isVisible():
            self.mini.move(self.frameGeometry().topRight()-self.mini.rect().topRight())
        self.mini.show()
        self.hide()
        self.mini.raise_()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.WindowStateChange and self.isMinimized() and hasattr(self,"tray"):
            if self.ctrl.settings.tray and self.tray.isSystemTrayAvailable():
                QTimer.singleShot(0,lambda:self.hide() if self.isMinimized() else None)

    def nativeEvent(self,event_type,message):
        msg=wintypes.MSG.from_address(int(message))
        if msg.message==0x0218 and msg.wParam==4 and hasattr(self,"timer"):
            self.advance("suspend")
        return super().nativeEvent(event_type,message)

    def closeEvent(self,event):
        try:
            self.advance("closed")
        except sqlite3.Error as exc:
            event.ignore()
            self.db_error(exc)
            return
        self.timer.stop()
        self.tray.hide()
        self.mini.hide()
        self.audio.close()
        event.accept()
        QApplication.instance().quit()
