from datetime import date, datetime, timedelta
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QWidget,QCheckBox,QComboBox,QSpinBox,QSlider,QScrollArea,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QFileDialog,QMessageBox)
from .config import LIMITS, VOICES
from .storage import STATUS
from .visual import font, LIGHT, DARK
from .widgets import box, button, label, card


def duration(ms):
    s = ms // 1000
    if s < 60:
        return f"{s} 秒"
    if s < 3600:
        return f"{s//60} 分 {s%60:02} 秒"
    return f"{s//3600} 时 {s%3600//60:02} 分"


class Preferences(QScrollArea):
    def __init__(self, window):
        super().__init__()
        self.w = window
        self.fields = {}
        self.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("form")
        self.setWidget(body)
        self.layout_ = box(body, margins=(0,0,6,6),spacing=14)
        self.section("计时方案", "修改后从下一轮开始使用")
        for key,name,unit in [
            ("focus","专注周期"," 分钟"),("long","长休息"," 分钟"),
            ("low","随机间隔下限"," 分钟"),("high","随机间隔上限"," 分钟"),
            ("micro","微休息时长"," 秒")]:
            w = QSpinBox()
            w.setRange(*LIMITS[key])
            w.setValue(getattr(window.ctrl.settings,key))
            w.setSuffix(unit)
            w.setKeyboardTracking(False)
            w.valueChanged.connect(lambda v,k=key:self.change(k,v))
            self.row(key,name,w)
        for key,name in [("micro_on","启用随机微休息"),("inclusive","微休息计入专注周期"),
                         ("auto_long","周期结束后自动进入长休息")]:
            self.check(key,name)
        self.section("声音与提醒")
        self.check("audio","启用提示音")
        voice=QComboBox()
        voice.addItems(VOICES)
        voice.setCurrentText(window.ctrl.settings.voice)
        voice.currentTextChanged.connect(lambda v:self.change("voice",v))
        self.row("voice","音色",voice)
        slider=QSlider(Qt.Horizontal)
        slider.setRange(0,100)
        slider.setValue(window.ctrl.settings.volume)
        slider.setFixedWidth(130)
        slider.setTracking(False)
        self.volname=label(f"音量 · {slider.value()}%")
        slider.valueChanged.connect(lambda v:self.change("volume",v))
        self.row("volume",self.volname,slider)
        previews = box(horizontal=True)
        for key,title in [("micro_start","微休息"),("resume_focus","恢复专注"),("long_start","长休息"),("long_end","结束")]:
            previews.addWidget(button(title,handler=lambda _,k=key:window.play(k)))
        self.group.addWidget(label("试听阶段提示音","muted"))
        self.group.addLayout(previews)
        self.check("notify","显示桌面通知")
        self.section("窗口与外观")
        self.check("dark","深色模式")
        self.check("pinned","主窗口置顶")
        self.check("tray","最小化时收入系统托盘")
        self.layout_.addStretch()

    def section(self,title,note=None):
        w=card()
        self.group=box(w,margins=18,spacing=9)
        self.group.addWidget(label(title,"head"))
        if note:
            self.group.addWidget(label(note,"muted"))
        self.layout_.addWidget(w)

    def row(self,key,title,w):
        self.fields[key]=w
        row=box(horizontal=True)
        name=label(title) if isinstance(title,str) else title
        w.setAccessibleName(name.text())
        row.addWidget(name)
        row.addStretch()
        row.addWidget(w)
        self.group.addLayout(row)

    def check(self,key,title):
        w=QCheckBox(title)
        w.setChecked(getattr(self.w.ctrl.settings,key))
        w.toggled.connect(lambda v:self.change(key,v))
        self.fields[key]=w
        self.group.addWidget(w)

    def change(self,key,value):
        values={key:value}
        cfg=self.w.ctrl.settings
        if key=="low" and value>cfg.high:
            values["high"]=value
        if key=="high" and value<cfg.low:
            values["low"]=value
        self.w.configure(**values)

    def sync(self):
        cfg=self.w.ctrl.settings
        for key,w in self.fields.items():
            val=getattr(cfg,key)
            w.blockSignals(True)
            if isinstance(w,QCheckBox): w.setChecked(val)
            elif isinstance(w,QComboBox): w.setCurrentText(val)
            else: w.setValue(val)
            w.blockSignals(False)
        self.volname.setText(f"音量 · {cfg.volume}%")


def periods(mode, today):
    if mode == 0:
        return [(d,d,d.strftime("%m/%d")) for d in
                [today-timedelta(days=i) for i in range(6,-1,-1)]]
    if mode == 1:
        monday=today-timedelta(days=today.weekday())
        return [(d,d+timedelta(days=6),d.strftime("%m/%d")) for d in
                [monday-timedelta(weeks=i) for i in range(7,-1,-1)]]
    items=[]
    end=(today.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    for _ in range(6):
        first=end.replace(day=1)
        items.insert(0,(first,end,f"{first.month} 月"))
        end=first-timedelta(days=1)
    return items


class Chart(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(115)
        self.items=[]
        self.colors=LIGHT
    def paintEvent(self,event):
        if not self.items: return
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c=self.colors
        p.setFont(font(11))
        p.setPen(QColor(c["line"]))
        baseline=self.height()-25
        p.drawLine(0,baseline,self.width(),baseline)
        cell=self.width()/len(self.items)
        peak=max(1,max(v for _,v in self.items))
        for i,(name,value) in enumerate(self.items):
            h=value/peak*(baseline-25)
            x=(i+.5)*cell
            width=min(36,cell*.48)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["accent"] if i==len(self.items)-1 else c["track"]))
            p.drawRoundedRect(QRectF(x-width/2,baseline-max(h,2),width,max(h,2)),3,3)
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(x-cell/2,baseline+3,cell,20),Qt.AlignCenter,name)
            if value:
                p.drawText(QRectF(x-cell/2,baseline-h-21,cell,20),Qt.AlignCenter,f"{value/60000:.1f}")
        p.end()


class Statistics(QWidget):
    def __init__(self,window):
        super().__init__()
        self.w=window
        self.offset=0
        layout=box(self,spacing=12)
        top=card()
        col=box(top,margins=16)
        row=box(horizontal=True)
        row.addWidget(label("实际专注趋势","head"))
        row.addWidget(label("分钟","muted"))
        row.addStretch()
        self.period=QComboBox()
        self.period.addItems(["按日","按周","按月"])
        self.period.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.period)
        col.addLayout(row)
        self.chart=Chart()
        col.addWidget(self.chart)
        self.total=label("","muted")
        col.addWidget(self.total)
        layout.addWidget(top)
        panel=card()
        col=box(panel,margins=16)
        row=box(horizontal=True)
        row.addWidget(label("学习记录","head"))
        row.addStretch()
        self.export_button=button("导出 CSV",handler=self.export)
        row.addWidget(self.export_button)
        col.addLayout(row)
        self.table=QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(["开始时间","实际专注","微休息","长休息","状态"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        col.addWidget(self.table,1)
        row=box(horizontal=True)
        self.info=label("","muted")
        row.addWidget(self.info)
        row.addStretch()
        self.prev=button("上一页",handler=lambda:self.page(-1))
        self.next=button("下一页",handler=lambda:self.page(1))
        row.addWidget(self.prev)
        row.addWidget(self.next)
        col.addLayout(row)
        layout.addWidget(panel,1)

    def page(self,direction):
        self.offset=max(0,self.offset+25*direction)
        self.refresh()

    def refresh(self,*_):
        mode=self.period.currentIndex()
        groups=periods(mode,date.today())
        rows=self.w.ctrl.store.daily(groups[0][0],groups[-1][1])
        values=[(name,sum(v[0] for k,v in rows.items() if str(a)<=k<=str(b))) for a,b,name in groups]
        self.chart.items=values
        self.chart.colors=DARK if self.w.ctrl.settings.dark else LIGHT
        self.chart.update()
        self.total.setText(["今日","本周","本月"][mode]+"实际专注   "+duration(values[-1][1]))
        records=self.w.ctrl.store.history(26,self.offset)
        self.prev.setEnabled(self.offset>0)
        self.next.setEnabled(len(records)>25)
        visible=records[:25]
        self.table.setRowCount(len(visible))
        for i,(start,status,focus,micro,long,count,completed) in enumerate(visible):
            values=[datetime.fromtimestamp(start/1000).strftime("%Y-%m-%d %H:%M"),
                    duration(focus),duration(micro),duration(long),STATUS[status]]
            for j,value in enumerate(values):
                self.table.setItem(i,j,QTableWidgetItem(value))
        self.info.setText(f"第 {self.offset+1}–{self.offset+len(visible)} 条" if visible else "还没有学习记录")

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,"导出学习记录","NeuroFocus-学习记录.csv","CSV (*.csv)")
        if path:
            try:
                self.w.advance("flush")
                self.w.ctrl.store.export(path)
            except OSError as exc:
                QMessageBox.warning(self,"导出失败",str(exc))
