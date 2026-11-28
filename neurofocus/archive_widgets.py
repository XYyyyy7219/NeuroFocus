from datetime import date, datetime, timedelta
import sqlite3
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QAbstractListModel, QModelIndex
from PySide6.QtGui import QPainter,QPen,QColor
from PySide6.QtWidgets import (QWidget,QDialog,QLineEdit,QPlainTextEdit,QComboBox,QMessageBox,
                               QScrollArea,QGraphicsView,QGraphicsScene,QVBoxLayout,QDialogButtonBox)
from .widgets import box,label,button
from .history import save_note, wall_time, session_detail, EVENTS
from .distribution import short_time


class ActivityList(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.rows=[]
        self.tags={}
    def replace(self,rows,tags):
        self.beginResetModel()
        self.rows,self.tags=rows,tags
        self.endResetModel()
    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)
    def data(self,index,role):
        if not index.isValid(): return
        a=self.rows[index.row()]
        if role==Qt.DisplayRole:
            topic=a.note[0] or self.tags[a.tag].name
            return f"{a.day}   {wall_time(a.started)}     {topic}   ·   {short_time(a.ms)}" + ("   ◉" if any(a.note) else "")
        if role==Qt.ToolTipRole: return a.note[1] or self.tags[a.tag].name


class Timeline(QGraphicsView):
    picked=Signal(object)
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(170)
        self.rows=[]
        self.tags={}
        self.start=date.today()
        self.n=1
        self.markers=[]
        self.setAccessibleName("按实际时间绘制的学习活动")
    def render_rows(self,rows,tags,start,n,markers=()):
        self.markers=markers
        self.rows,self.tags,self.start,self.n=rows,tags,start,n
        self.redraw()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"n"): self.redraw()
    def changeEvent(self,event):
        super().changeEvent(event)
        if hasattr(self,"n") and event.type()==QEvent.PaletteChange:
            QTimer.singleShot(0,self.redraw)
    def redraw(self):
        scene=self.scene()
        scene.clear()
        w=max(220,self.viewport().width()-20)
        col=(w-52)/self.n
        clock=self.palette().text().color()
        def caption(x,y,text,color):
            t=scene.addSimpleText(text)
            t.setBrush(color)
            t.setPos(x,y)
            return t
        if not self.rows and not self.markers:
            caption(12,18,"此日期范围没有学习活动",clock)
            scene.setSceneRect(0,0,w,80)
            return
        def minute(ms,day):
            dt=datetime.fromtimestamp(ms/1000)
            return (dt.date()-day).days*1440+dt.hour*60+dt.minute+dt.second/60+dt.microsecond/6e7
        timed=[(a,minute(a.started,date.fromisoformat(a.day)),minute(a.ended,date.fromisoformat(a.day)))
               for a in self.rows if a.started is not None]
        marker_minutes=[minute(at,datetime.fromtimestamp(at/1000).date()) for at,_,_ in self.markers]
        low=max(0,int(min([x[1] for x in timed]+marker_minutes,default=8*60)//60))
        high=min(24,max(low+1,int(max([x[2] for x in timed]+marker_minutes,default=9*60)//60)+1))
        scale=max(.06,min(2.5,(self.viewport().height()-62)/max(60,60*(high-low))))
        y=lambda m: 32+(m-60*low)*scale
        for i in range(self.n):
            caption(52+col*i,3,(self.start+timedelta(days=i)).strftime("%m/%d"),clock)
        label_step=max(1,round(24/(60*scale)))
        for h in range(low,high+1,label_step):
            caption(0,y(60*h)-8,f"{h:02d}:00",clock)
            scene.addLine(50,y(60*h),w,y(60*h),QPen(self.palette().mid().color(),.6))
        for a,begin,end in timed:
            x=53+(date.fromisoformat(a.day)-self.start).days*col
            color=QColor(self.tags[a.tag].color)
            fill=QColor(color)
            fill.setAlpha(72)
            height=max(2,y(end)-y(begin))
            item=scene.addRect(x,y(begin),max(4,col-5),height,QPen(color),fill)
            item.setData(0,a.key)
            tip=f"{a.mode_name} · {a.note[0] or self.tags[a.tag].name}　{wall_time(a.started)}–{wall_time(a.ended)}　有效 {short_time(a.ms)}"
            item.setToolTip(tip)
            if height>20 and col>72:
                title=caption(x+4,y(begin),self.fontMetrics().elidedText(("◉ " if any(a.note) else "")+(a.note[0] or self.tags[a.tag].name),Qt.ElideRight,int(col-12)),clock)
                title.setData(0,a.key)
                title.setToolTip(tip)
        for at,kind,mode in self.markers:
            day=datetime.fromtimestamp(at/1000).date()
            x=53+(day-self.start).days*col
            colors={"micro_start":"#6D9C89","short_start":"#C39062","long_start":"#728FB8","manual_start":"#9C85B1"}
            mark=scene.addRect(x,y(minute(at,day)),max(7,col*.16),3,QPen(Qt.NoPen),QColor(colors[kind]))
            mark.setToolTip(f"{wall_time(at)} · {EVENTS[kind]} · {mode}")
        if len(timed)<len(self.rows): caption(52,y(high*60)+15,"旧版日汇总见下方列表",clock)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(0,0,3,5))
    def mousePressEvent(self,e):
        hit=self.itemAt(e.position().toPoint())
        if hit and hit.data(0): self.picked.emit(tuple(hit.data(0)))
        super().mousePressEvent(e)


class JournalEditor(QDialog):
    def __init__(self,parent,db,a,tag):
        super().__init__(parent)
        self.db,self.key=db,a.key
        self.setWindowTitle("学习日志")
        self.resize(510,410)
        col=box(self,margins=18)
        col.addWidget(label(f"{a.day}　{tag}　·　实际学习 {short_time(a.ms)}","head"))
        summary=button("本轮参数与休息 · "+a.mode_name)
        detail=QPlainTextEdit(session_detail(db,a))
        detail.setReadOnly(True)
        detail.setMaximumHeight(115)
        detail.hide()
        summary.clicked.connect(lambda:detail.setVisible(detail.isHidden()))
        col.addWidget(summary,0,Qt.AlignLeft)
        col.addWidget(detail)
        self.topic=QLineEdit(a.note[0])
        self.gain=QPlainTextEdit(a.note[1])
        self.gain.setPlaceholderText("一句话记下理解了什么，或完成了什么")
        col.addWidget(label("学习主题"))
        col.addWidget(self.topic)
        col.addWidget(label("学习收获"))
        col.addWidget(self.gain)
        self.more=QWidget()
        extra=box(self.more)
        self.question=QPlainTextEdit(a.note[2])
        self.next_step=QPlainTextEdit(a.note[3])
        self.experience=QComboBox()
        self.experience.addItems(["","疲劳","一般","良好","投入"])
        self.experience.setCurrentText(a.note[4])
        for name,w in (("疑问与思考",self.question),("下一步",self.next_step),("学习体验",self.experience)):
            extra.addWidget(label(name))
            extra.addWidget(w)
        toggle=button("深度日志",handler=lambda:self.more.setVisible(toggle.isChecked()))
        toggle.setCheckable(True)
        toggle.setChecked(any(a.note[2:]))
        col.addWidget(toggle)
        col.addWidget(self.more)
        self.more.setVisible(toggle.isChecked())
        self.status=label("可使用 Markdown 记录；草稿自动保存在本机","muted")
        row=box(horizontal=True)
        row.addWidget(self.status,1)
        row.addWidget(button("完成",handler=self.accept))
        col.addLayout(row)
        self.dirty=False
        self.timer=QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.flush)
        for signal in (self.topic.textChanged,self.gain.textChanged,self.question.textChanged,
                       self.next_step.textChanged,self.experience.currentTextChanged):
            signal.connect(self.edited)
    def edited(self,*_):
        self.dirty=True
        self.timer.start(450)
        self.status.setText("正在保存…")
    def flush(self):
        if not self.dirty: return True
        values=(self.topic.text().strip(),self.gain.toPlainText(),self.question.toPlainText(),
                self.next_step.toPlainText(),self.experience.currentText())
        try: save_note(self.db,self.key,values)
        except sqlite3.Error as exc:
            self.status.setText(f"草稿尚未保存：{exc}")
            return False
        self.dirty=False
        self.status.setText("已保存到本机")
        return True
    def done(self,result):
        if self.flush(): super().done(result)
