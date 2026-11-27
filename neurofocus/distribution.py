"""Interactive tag distribution using the same Qt painter and palette as the timer."""
from datetime import date, timedelta
from math import atan2, hypot, pi

from PySide6.QtCore import Qt, Signal, QDate, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QWidget,QComboBox,QDateEdit,QScrollArea,QToolTip,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QStyledItemDelegate)
from .visual import LIGHT,DARK,font
from .widgets import box,button,label,card
from .tags import grouped_days
from .tag_ui import swatch,show_detail,TagManager


def short_time(ms):
    seconds = int(ms)//1000
    if seconds>=3600: return f"{seconds//3600}时{seconds%3600//60:02}分"
    if seconds>=60: return f"{seconds//60}分{seconds%60:02}秒"
    if 0<ms<1000: return f"{ms/1000:.2g}秒"
    return f"{seconds}秒"


class Ring(QWidget):
    chosen = Signal(int)
    def __init__(self):
        super().__init__()
        self.rows = []
        self.colors = LIGHT
        self.total = 0
        self.setMinimumHeight(145)
        self.setMouseTracking(True)
        self.setAccessibleName("学习时长占比环形图")

    def radius(self):
        return min(self.width(),self.height(),205)*0.38

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.radius()
        p.translate(self.width()/2,self.height()/2)
        rect = QRectF(-r,-r,2*r,2*r)
        p.setPen(QPen(QColor(self.colors["track"]),r*.25))
        p.drawEllipse(rect)
        angle = 90*16
        cumulative = 0
        for tag,ms,_,__ in self.rows:
            cumulative += ms
            stop = 90*16-round(5760*cumulative/self.total)
            p.setPen(QPen(QColor(tag.color),r*.25,Qt.SolidLine,Qt.FlatCap))
            p.drawArc(rect,angle,stop-angle)
            angle = stop
        p.setFont(font(12))
        p.setPen(QColor(self.colors["muted"]))
        p.drawText(QRectF(-r,-26,2*r,23),Qt.AlignCenter,"实际学习")
        p.setFont(font(17))
        p.setPen(QColor(self.colors["ink"]))
        p.drawText(QRectF(-r,-3,2*r,32),Qt.AlignCenter,short_time(self.total))
        p.end()

    def hit(self,pos):
        x,y = pos.x()-self.width()/2,pos.y()-self.height()/2
        r = self.radius()
        if not r*.86<=hypot(x,y)<=r*1.14: return None
        point = ((atan2(x,-y)/(2*pi))%1)*self.total
        for tag,ms,ratio,_ in self.rows:
            point -= ms
            if point<0: return tag,ms,ratio

    def mouseMoveEvent(self,event):
        hit = self.hit(event.position())
        if hit:
            tag,ms,ratio = hit
            from html import escape
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"<b>{escape(tag.name)}</b> · {short_time(ms)} · {ratio:.1%}",self)
        else: QToolTip.hideText()

    def mousePressEvent(self,event):
        hit = self.hit(event.position())
        if hit and event.button()==Qt.LeftButton: self.chosen.emit(hit[0].id)


def period_start(day, mode):
    if mode=="周": return day-timedelta(days=day.weekday())
    if mode=="月": return day.replace(day=1)
    return day


def shift(day,mode,count):
    if mode=="月":
        year,month = divmod(day.year*12+day.month-1+count,12)
        return date(year,month+1,1)
    return day+timedelta(days=count*(7 if mode=="周" else 1))


class Columns(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(123)
        self.bars = []
        self.tags = {}
        self.colors = LIGHT
        self.setMouseTracking(True)
    def paintEvent(self,event):
        if not self.bars: return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.height()-24
        cell = self.width()/len(self.bars)
        peak = max(1,max(sum(v.values()) for _,v in self.bars))
        p.setFont(font(10))
        p.setPen(QColor(self.colors["line"]))
        p.drawLine(0,base,self.width(),base)
        for i,(day,values) in enumerate(self.bars):
            x,y = (i+.5)*cell,float(base)
            width = min(36,cell*.62)
            for key,ms in sorted(values.items()):
                h = ms/peak*(base-22)
                y -= h
                p.fillRect(QRectF(x-width/2,y,width,h),QColor(self.tags[key].color))
            p.setPen(QColor(self.colors["muted"]))
            if values:
                p.drawText(QRectF(x-cell/2,y-19,cell,18),Qt.AlignCenter,f"{sum(values.values())/60000:.1f}")
            p.drawText(QRectF(x-cell/2,base+2,cell,20),Qt.AlignCenter,day.strftime("%m/%d"))
        p.end()
    def mouseMoveEvent(self,event):
        if not self.bars: return
        i = min(len(self.bars)-1,int(event.position().x()*len(self.bars)/max(1,self.width())))
        day,values = self.bars[i]
        from html import escape
        lines = [f"{escape(self.tags[k].name)} · {short_time(ms)}" for k,ms in values.items()]
        QToolTip.showText(event.globalPosition().toPoint(),"<b>"+str(day)+"</b><br>"+"<br>".join(lines or ["0 秒"]),self)


class Trend(QWidget):
    def __init__(self):
        super().__init__()
        self.daily = []
        self.start = self.end = date.today()
        self.offset = 0
        col = box(self)
        row = box(horizontal=True)
        row.addWidget(label("学习趋势 · 分钟","muted"))
        row.addStretch()
        self.mode = QComboBox()
        self.mode.addItems(["日","周","月"])
        row.addWidget(self.mode)
        self.prev = button("‹",handler=lambda:self.turn(1))
        self.next = button("›",handler=lambda:self.turn(-1))
        self.prev.setAccessibleName("较早时间段")
        self.next.setAccessibleName("较晚时间段")
        row.addWidget(self.prev)
        row.addWidget(self.next)
        col.addLayout(row)
        self.plot = Columns()
        col.addWidget(self.plot)
        self.mode.currentIndexChanged.connect(self.reset)

    def set_data(self,daily,tags,start,end,dark):
        if (start,end)!=(self.start,self.end): self.offset=0
        self.daily,self.start,self.end = daily,start,end
        self.plot.tags,self.plot.colors = tags,DARK if dark else LIGHT
        self.refresh()
    def reset(self):
        self.offset=0
        self.refresh()
    def turn(self,delta):
        self.offset=max(0,self.offset+delta)
        self.refresh()
    def refresh(self):
        mode=self.mode.currentText()
        chunks=dict(grouped_days(self.daily,mode))
        first=period_start(self.start,mode)
        last=shift(period_start(self.end,mode),mode,-8*self.offset)
        visible=[shift(last,mode,i) for i in range(-7,1)]
        self.plot.bars=[(d,chunks.get(d,{})) for d in visible if first<=d]
        self.prev.setEnabled(first<visible[0])
        self.next.setEnabled(self.offset>0)
        self.plot.update()


class DurationBar(QStyledItemDelegate):
    def paint(self,painter,option,index):
        super().paint(painter,option,index)
        values=index.data(Qt.UserRole)
        if values:
            color,fraction=values
            rect=option.rect
            painter.fillRect(QRectF(rect.left()+4,rect.bottom()-3,
                                    max(1,(rect.width()-9)*fraction),3),QColor(color))


class Distribution(QScrollArea):
    def __init__(self,window):
        super().__init__()
        self.w=window
        self.tags=window.ctrl.store.tags
        self.setWidgetResizable(True)
        body=QWidget()
        body.setObjectName("form")
        self.setWidget(body)
        col=box(body,margins=(0,8,5,5),spacing=10)
        row=box(horizontal=True)
        self.range=QComboBox()
        self.range.addItems(["今日","本周","本月","本年","全部","自定义"])
        row.addWidget(self.range)
        row.addStretch()
        row.addWidget(button("管理标签",handler=self.manage))
        col.addLayout(row)
        self.dates=QWidget()
        dates=box(self.dates,horizontal=True)
        self.a,self.b=QDateEdit(QDate.currentDate()),QDateEdit(QDate.currentDate())
        for title,edit in [("起",self.a),("至",self.b)]:
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            dates.addWidget(label(title))
            dates.addWidget(edit)
        dates.addStretch()
        col.addWidget(self.dates)
        panel=card()
        group=box(panel,margins=14)
        self.ring=Ring()
        group.addWidget(self.ring)
        self.summary=label("","muted")
        group.addWidget(self.summary)
        self.table=QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["学习标签","实际学习","占比","日均"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.setItemDelegateForColumn(1,DurationBar(self.table))
        group.addWidget(self.table)
        col.addWidget(panel)
        panel=card()
        group=box(panel,margins=14)
        self.trend=Trend()
        group.addWidget(self.trend)
        col.addWidget(panel)
        col.addStretch()
        self.table.cellClicked.connect(lambda i,j:self.detail(self.ring.rows[i][0].id))
        self.table.cellActivated.connect(lambda i,j:self.detail(self.ring.rows[i][0].id))
        self.ring.chosen.connect(self.detail)
        self.range.currentIndexChanged.connect(self.refresh)
        self.a.dateChanged.connect(self.refresh)
        self.b.dateChanged.connect(self.refresh)

    def manage(self):
        TagManager(self.w).exec()
        self.refresh()
    def detail(self,key):
        tag=next(t for t in self.tags.all() if t.id==key)
        show_detail(self.w,tag,self.start,self.end)
    def refresh(self,*_):
        mode=self.range.currentText()
        self.dates.setVisible(mode=="自定义")
        dates=self.a.date().toPython(),self.b.date().toPython()
        try:
            self.start,self.end=self.tags.bounds(mode,date.today(),dates)
            rows,daily,total=self.tags.report(self.start,self.end)
            message=f"{self.start} 至 {self.end}   ·   "+("点击标签查看记录" if rows else "此期间没有学习记录")
        except ValueError as error:
            rows,daily,total=[],[],0
            self.start=self.end=date.today()
            message=str(error)
        self.summary.setText(message)
        self.ring.rows,self.ring.total=rows,total
        self.ring.colors=DARK if self.w.ctrl.settings.dark else LIGHT
        self.ring.update()
        self.table.setRowCount(len(rows))
        self.table.setFixedHeight(42+min(7,len(rows))*32)
        for i,(tag,ms,pct,avg) in enumerate(rows):
            self.table.setItem(i,0,QTableWidgetItem(swatch(tag.color),tag.name+("（已归档）" if tag.archived else "")))
            amount=QTableWidgetItem(short_time(ms))
            amount.setData(Qt.UserRole,(tag.color,ms/rows[0][1]))
            self.table.setItem(i,1,amount)
            self.table.setItem(i,2,QTableWidgetItem(f"{pct:.1%}"))
            self.table.setItem(i,3,QTableWidgetItem(short_time(avg)))
        self.trend.set_data(daily,{t.id:t for t in self.tags.all()},self.start,self.end,self.w.ctrl.settings.dark)
