from datetime import date, datetime, timedelta
from html import escape

from PySide6.QtCore import Qt,QDate,QRectF,Signal
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import (QWidget,QScrollArea,QComboBox,QSpinBox,QDateEdit,
    QDialog,QListWidget,QListWidgetItem,QToolTip,QTableWidget,QTableWidgetItem,
    QHeaderView,QAbstractItemView)
from .calendar_data import CalendarData,Day,level,position,records,rolling
from .distribution import Ring,short_time
from .tag_ui import swatch
from .visual import LIGHT,DARK,font
from .widgets import box,button,label,card

WEEK="一二三四五六日"
PALETTES=(("#e0e6df","#bad4c0","#82b797","#4a8d69","#225c44"),
          ("#314037","#385b49","#548464","#80b58d","#b5e0bc"))
DAY=timedelta(days=1)


class Heatmap(QWidget):
    picked=Signal(object)
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("学习热力图，左右键移动一天，上下键移动一周")
        self.first=self.last=self.today=self.selected=date.today()
        self.hover=None
        self.days=self.tags={}
        self.dark=False
        self.cuts=(30,90,180)
        self.setFixedHeight(167)

    @property
    def columns(self):
        return position(self.first,self.last)[0]+1

    @property
    def pitch(self):
        return min(18,max(14,(self.width()-12)//self.columns))

    def at(self,p):
        x,y=p.x()-2,p.y()-30
        if x<0 or y<0: return None
        col,dx=divmod(int(x),self.pitch)
        row,dy=divmod(int(y),self.pitch)
        if row>6 or dx>=self.pitch-3 or dy>=self.pitch-3: return None
        ordinal=self.first.toordinal()-self.first.weekday()+col*7+row
        if self.first.toordinal()<=ordinal<=self.last.toordinal(): return date.fromordinal(ordinal)

    def rect_for(self,d):
        col,row=position(self.first,d)
        p=self.pitch
        return QRectF(2+col*p,30+row*p,p-3,p-3)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        theme=DARK if self.dark else LIGHT
        colors=PALETTES[self.dark]
        pitch=self.pitch
        p.setFont(font(11))
        p.setPen(QColor(theme["muted"]))
        clip=event.rect()
        start=self.first.toordinal()-self.first.weekday()
        last_label=-1000
        for col in range(max(0,(clip.left()-40)//pitch),min(self.columns,clip.right()//pitch+2)):
            for row in range(7):
                ordinal=start+col*7+row
                if not self.first.toordinal()<=ordinal<=self.last.toordinal(): continue
                d=date.fromordinal(ordinal)
                rect=self.rect_for(d)
                if (d==self.first or d.day==1) and rect.left()-last_label>=31:
                    p.setPen(QColor(theme["muted"]))
                    p.drawText(QRectF(rect.left(),3,36,22),Qt.AlignLeft,f"{d.month}月")
                    last_label=rect.left()
                item=self.days.get(d)
                future=d>self.today
                p.setBrush(Qt.NoBrush if future else QColor(colors[level(item.ms if item else 0,self.cuts)]))
                if d==self.selected or d==self.hover:
                    p.setPen(QPen(QColor(theme["ink"]),2 if d==self.selected else 1))
                elif future: p.setPen(QPen(QColor(theme["line"]),1,Qt.DotLine))
                else: p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect,2.5,2.5)
        p.end()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"weekdays"): self.weekdays.update()

    def mouseMoveEvent(self,e):
        d=self.at(e.position())
        if d!=self.hover:
            self.hover=d
            self.update()
        if d is None:
            QToolTip.hideText()
            return
        item=self.days.get(d,Day())
        lines=[f"<b>{d} 星期{WEEK[d.weekday()]}</b>"]
        if d>self.today: lines.append("未来日期")
        else:
            lines.append(f"实际学习 {short_time(item.ms)} · 涉及 {item.cycles} 个周期")
            lines.extend(f"{escape(self.tags[k].name)}　{short_time(v)}" for k,v in item.tags.most_common())
        QToolTip.showText(e.globalPosition().toPoint(),"<br>".join(lines),self)
    def leaveEvent(self,e):
        self.hover=None
        self.update()
    def mousePressEvent(self,e):
        d=self.at(e.position())
        if d and e.button()==Qt.LeftButton: self.picked.emit(d)
    def keyPressEvent(self,e):
        offsets={Qt.Key_Left:-1,Qt.Key_Right:1,Qt.Key_Up:-7,Qt.Key_Down:7}
        if e.key() in offsets:
            n=self.selected.toordinal()+offsets[e.key()]
            if self.first.toordinal()<=n<=self.last.toordinal(): self.picked.emit(date.fromordinal(n))
        else: super().keyPressEvent(e)


class Weekdays(QWidget):
    def __init__(self,grid):
        super().__init__()
        self.grid=grid
        self.setFixedWidth(31)
    def paintEvent(self,event):
        p=QPainter(self)
        p.setFont(font(11))
        p.setPen(QColor((DARK if self.grid.dark else LIGHT)["muted"]))
        for row,name in enumerate(WEEK):
            pitch=self.grid.pitch
            p.drawText(QRectF(0,28+row*pitch,30,pitch),Qt.AlignCenter,"周"+name)
        p.end()


class StudyCalendar(QScrollArea):
    def __init__(self,w):
        super().__init__()
        self.w=w
        self.store=w.ctrl.store
        self.filter=None
        self.selected=date.today()
        self.page=0
        self.cache=None
        self.setWidgetResizable(True)
        body=QWidget()
        body.setObjectName("form")
        self.setWidget(body)
        layout=box(body,margins=(0,8,4,4),spacing=10)
        top=card()
        col=box(top,margins=14)
        row=box(horizontal=True)
        self.mode=QComboBox()
        self.mode.addItems(["最近 3 个月","最近 6 个月","最近 12 个月","自然年","自定义"])
        self.mode.setCurrentIndex(2)
        row.addWidget(self.mode)
        self.back=button("‹",handler=lambda:self.go_year(-1))
        self.forward=button("›",handler=lambda:self.go_year(1))
        self.back.setToolTip("上一年")
        self.forward.setToolTip("下一年")
        self.year=QSpinBox()
        self.year.setRange(1900,9999)
        self.year.setValue(date.today().year)
        for obj in (self.back,self.year,self.forward): row.addWidget(obj)
        row.addStretch()
        row.addWidget(button("今天",handler=self.today))
        col.addLayout(row)
        self.custom=QWidget()
        dates=box(self.custom,horizontal=True)
        self.a=QDateEdit(QDate.currentDate().addMonths(-3))
        self.b=QDateEdit(QDate.currentDate())
        for name,edit in [("从",self.a),("至",self.b)]:
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            dates.addWidget(label(name))
            dates.addWidget(edit)
        dates.addStretch()
        col.addWidget(self.custom)
        row=box(horizontal=True)
        self.range_label=label("","muted")
        row.addWidget(self.range_label)
        row.addStretch()
        self.filter_btn=button("全部标签",handler=self.choose_tags)
        row.addWidget(self.filter_btn)
        row.addWidget(button("色阶",handler=self.thresholds))
        col.addLayout(row)
        self.grid=Heatmap()
        self.grid.picked.connect(self.pick)
        self.scroller=QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroller.setFixedHeight(184)
        self.scroller.setWidget(self.grid)
        gridrow=box(horizontal=True,spacing=2)
        self.grid.weekdays=Weekdays(self.grid)
        gridrow.addWidget(self.grid.weekdays)
        gridrow.addWidget(self.scroller,1)
        col.addLayout(gridrow)
        self.legend=label("","muted")
        self.legend.setWordWrap(True)
        col.addWidget(self.legend)
        layout.addWidget(top)
        panel=card()
        col=box(panel,margins=14)
        self.summary=label("","head")
        self.means=label("","muted")
        self.subjects=label("")
        self.subjects.setTextFormat(Qt.PlainText)
        for obj in (self.summary,self.means,self.subjects):
            obj.setWordWrap(True)
            col.addWidget(obj)
        layout.addWidget(panel)
        panel=card()
        col=box(panel,margins=14)
        row=box(horizontal=True)
        self.heading=label("","head")
        row.addWidget(self.heading)
        row.addStretch()
        self.prev_day=button("前一天",handler=lambda:self.pick(self.selected-DAY))
        self.next_day=button("后一天",handler=lambda:self.pick(self.selected+DAY))
        row.addWidget(self.prev_day)
        row.addWidget(self.next_day)
        col.addLayout(row)
        self.note=label("","muted")
        self.note.setWordWrap(True)
        col.addWidget(self.note)
        self.ring=Ring()
        self.ring.setFixedHeight(145)
        col.addWidget(self.ring)
        self.breakdown=label("")
        self.breakdown.setWordWrap(True)
        col.addWidget(self.breakdown)
        self.table=QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["学习标签","开始","结束","实际时长"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        col.addWidget(self.table)
        row=box(horizontal=True)
        row.addStretch()
        self.prev=button("上一页",handler=lambda:self.turn(-1))
        self.next=button("下一页",handler=lambda:self.turn(1))
        row.addWidget(self.prev)
        row.addWidget(self.next)
        col.addLayout(row)
        layout.addWidget(panel)
        layout.addStretch()
        for signal in (self.mode.currentIndexChanged,self.year.valueChanged,self.a.dateChanged,self.b.dateChanged):
            signal.connect(self.refresh)

    def go_year(self,delta):
        base=self.year.value() if self.mode.currentIndex()==3 else self.selected.year
        self.year.setValue(base+delta)
        self.mode.setCurrentIndex(3)

    def today(self):
        self.selected=date.today()
        self.mode.setCurrentIndex(2)
        self.refresh()
        self.pick(self.selected)

    def choose_tags(self):
        dialog=QDialog(self)
        dialog.setWindowTitle("筛选学习标签")
        col=box(dialog,margins=14)
        items=QListWidget()
        col.addWidget(items)
        tags=self.store.tags.all()
        for t in tags:
            item=QListWidgetItem(swatch(t.color),t.name+(" · 已归档" if t.archived else ""))
            item.setCheckState(Qt.Checked if self.filter is None or t.id in self.filter else Qt.Unchecked)
            items.addItem(item)
        row=box(horizontal=True)
        def check(state):
            for i in range(items.count()): items.item(i).setCheckState(state)
        row.addWidget(button("全选",handler=lambda:check(Qt.Checked)))
        row.addWidget(button("清空",handler=lambda:check(Qt.Unchecked)))
        row.addWidget(button("应用",handler=dialog.accept))
        col.addLayout(row)
        if dialog.exec():
            chosen={t.id for i,t in enumerate(tags) if items.item(i).checkState()==Qt.Checked}
            self.filter=None if len(chosen)==len(tags) else chosen
            self.page=0
            self.refresh()

    def thresholds(self):
        dialog=QDialog(self)
        dialog.setWindowTitle("色阶上限（分钟）")
        col=box(dialog,margins=14)
        spins=[]
        for title,value in zip(["一级上限","二级上限","三级上限"],self.grid.cuts):
            row=box(horizontal=True)
            row.addWidget(label(title))
            spin=QSpinBox()
            spin.setRange(1,1440)
            spin.setValue(value)
            row.addWidget(spin)
            spins.append(spin)
            col.addLayout(row)
        tip=label("第四级为超过三级上限的日期","muted")
        col.addWidget(tip)
        def save():
            a,b,c=[s.value() for s in spins]
            if not a<b<c:
                tip.setText("三个上限必须逐级增加")
                return
            self.w.configure(calendar_low=a,calendar_mid=b,calendar_high=c)
            dialog.accept()
        col.addWidget(button("保存",handler=save))
        dialog.exec()
        self.refresh()

    def refresh(self,*_):
        today=date.today()
        index=self.mode.currentIndex()
        self.custom.setVisible(index==4)
        self.year.setVisible(index==3)
        if index<3:
            first,last=rolling(today,(3,6,12)[index])
        elif index==3:
            first,last=date(self.year.value(),1,1),date(self.year.value(),12,31)
        else:
            first,last=self.a.date().toPython(),self.b.date().toPython()
        valid=first<=last
        key=(first,last,today,self.store.db.total_changes,None if self.filter is None else frozenset(self.filter))
        old=self.cache
        if key!=old:
            self.tags={t.id:t for t in self.store.tags.all()}
            self.data=CalendarData(self.store.db,first,last,today,self.filter)
            self.cache=key
        self.range_label.setText(f"{first} — {last}" if valid else "开始日期须早于或等于结束日期")
        if self.filter is None: name="全部标签"
        elif len(self.filter)==1: name=self.tags[next(iter(self.filter))].name
        else: name=f"已选 {len(self.filter)} 个标签"
        self.filter_btn.setText(name[:14]+("…" if len(name)>14 else ""))
        self.filter_btn.setToolTip(name)
        self.selected=min(last,max(first,self.selected)) if valid else first
        self.grid.first,self.grid.last,self.grid.today=first,max(first,last),today
        self.grid.selected,self.grid.days,self.grid.tags=self.selected,self.data.days,self.tags
        cfg=self.w.ctrl.settings
        self.grid.dark=cfg.dark
        cuts=(cfg.calendar_low,cfg.calendar_mid,cfg.calendar_high)
        self.grid.cuts=cuts
        self.grid.setMinimumWidth(12+14*self.grid.columns)
        self.grid.update()
        self.grid.weekdays.setVisible(valid)
        self.grid.weekdays.update()
        self.scroller.setVisible(valid)
        colors=PALETTES[cfg.dark]
        levels=["0",f"(0, {cuts[0]}]",f"({cuts[0]}, {cuts[1]}]",f"({cuts[1]}, {cuts[2]}]",f">{cuts[2]}"]
        self.legend.setText("分钟　"+"　".join(f'<span style="color:{c}">■</span> {v}' for c,v in zip(colors,levels))+"　┄ 未来")
        d=self.data
        self.summary.setText(f"累计 {short_time(d.ms)}　·　学习 {d.active} 天　·　完成 {d.completed} 轮")
        self.means.setText(f"自然日日均（{d.elapsed} 天） {short_time(d.daily_mean)}　　学习日日均（{d.active} 天） {short_time(d.active_mean)}")
        self.subjects.setText("　 ·　".join(f"{self.tags[k].name} {short_time(v)}" for k,v in d.tags.most_common()))
        if not old or key[:2]!=old[:2]:
            self.page=0
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0,self.reveal)
        self.detail(valid)

    def reveal(self):
        cell=self.grid.rect_for(self.selected).center()
        self.scroller.ensureVisible(int(cell.x()),int(cell.y()),18,0)

    def pick(self,day):
        self.selected=self.grid.selected=day
        self.page=0
        self.grid.update()
        self.reveal()
        self.detail()

    def turn(self,direction):
        self.page+=direction
        self.detail()

    def detail(self,valid=True):
        d=self.selected
        item=self.data.days.get(d,Day())
        self.heading.setText(f"{d}　星期{WEEK[d.weekday()]}" if valid else "日期详情")
        self.prev_day.setEnabled(valid and d>self.grid.first)
        self.next_day.setEnabled(valid and d<self.grid.last)
        has=valid and d<=self.grid.today and (item.ms or item.cycles)
        text="未来日期" if d>self.grid.today else "当前筛选下没有学习记录"
        if has:
            text=(f"涉及 {item.cycles} 轮，完成 {item.completed} 轮　·　微休息 {item.micro} 次 / {short_time(item.short_ms)}"
                  f"　·　长休息 {short_time(item.long_ms)}")
            if self.filter is not None: text+="（休息和完成数按关联周期去重）"
        self.note.setText(text if valid else "请选择有效日期范围")
        self.ring.rows=[(self.tags[k],ms,ms/item.ms,ms) for k,ms in item.tags.most_common()]
        self.ring.total=item.ms
        self.ring.colors=DARK if self.grid.dark else LIGHT
        self.ring.update()
        self.breakdown.setText("　".join(f'<span style="color:{t.color}">●</span> {escape(t.name)} {short_time(ms)} · {ratio:.1%}'
                                        for t,ms,ratio,_ in self.ring.rows))
        rows=records(self.store.db,d,self.filter,self.page) if has and item.ms else []
        self.table.setRowCount(min(25,len(rows)))
        def fmt(ms):
            return "旧版日汇总" if ms is None else datetime.fromtimestamp(ms/1000).strftime("%H:%M:%S")
        for i,(_,key,a,b,ms) in enumerate(rows[:25]):
            for j,value in enumerate((self.tags[key].name,fmt(a),fmt(b),short_time(ms))):
                self.table.setItem(i,j,QTableWidgetItem(value))
        self.table.setFixedHeight(40+min(6,len(rows))*31)
        for obj in (self.table,self.ring,self.breakdown): obj.setVisible(bool(rows))
        self.prev.setVisible(self.page>0)
        self.next.setVisible(len(rows)>25)
