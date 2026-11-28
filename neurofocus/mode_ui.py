"""Focus policy selection, editing and per-mode projections."""
from dataclasses import replace
import sqlite3
from datetime import date,timedelta
from PySide6.QtCore import Qt,QDate
from PySide6.QtWidgets import (QAbstractItemView,QCheckBox,QComboBox,QDateEdit,QDialog,
    QDialogButtonBox,QFormLayout,QHeaderView,QLineEdit,QListWidget,QListWidgetItem,
    QMessageBox,QScrollArea,QSpinBox,QTableWidget,QTableWidgetItem,QWidget)
from .modes import NAMES,DESCRIPTIONS,ICONS,default
from .mode_stats import mode_totals
from .visual import icon
from .widgets import box,button,label
from .distribution import short_time


class ProfileEditor(QDialog):
    def __init__(self,parent,profile):
        super().__init__(parent)
        self.original=self.result_profile=profile
        self.setWindowTitle("配置专注模式")
        self.resize(470,540)
        col=box(self,margins=16)
        self.scroll=QScrollArea()
        self.scroll.setWidgetResizable(True)
        body=QWidget()
        body.setObjectName("form")
        self.form=QFormLayout(body)
        self.form.setVerticalSpacing(8)
        self.scroll.setWidget(body)
        col.addWidget(self.scroll,1)
        self.inputs={}
        self.custom=profile.id not in NAMES
        def field(key,title,widget):
            self.inputs[key]=widget
            widget.setAccessibleName(title)
            self.form.addRow(title,widget)
        def check(key,title):
            w=QCheckBox()
            w.setChecked(getattr(profile,key))
            w.setText("已开启" if w.isChecked() else "关闭")
            w.toggled.connect(lambda on,control=w:control.setText("已开启" if on else "关闭"))
            field(key,title,w)
            w.toggled.connect(self.visibility)
        def minutes(key,title,maximum=180,minimum=1,suffix=" 分钟",value=None):
            w=QSpinBox()
            w.setRange(minimum,maximum)
            w.setSuffix(suffix)
            w.setValue(getattr(profile,key) if value is None else value)
            field(key,title,w)
        name=QLineEdit(profile.name)
        name.setMaxLength(32)
        name.setReadOnly(not self.custom)
        field("name","模式名称",name)
        check("count_up","正向计时")
        minutes("focus","专注时长",720)
        if profile.id=="deep":
            quick=QWidget()
            row=box(quick,horizontal=True,spacing=3)
            for n in (30,45,60,90):
                row.addWidget(button(str(n),handler=lambda _,v=n:self.inputs["focus"].setValue(v)))
            self.form.addRow("快捷分钟",quick)
        minutes("long","长休息时长")
        check("short_on","使用短休息")
        minutes("short","短休息时长")
        check("grouped","分组计轮")
        minutes("rounds","每组周期",24,2," 轮")
        check("micro_on","随机微休息")
        minutes("low","随机间隔下限",120)
        minutes("high","随机间隔上限",120)
        minutes("micro","微休息时长",300,1," 秒")
        check("inclusive","微休息计入周期")
        check("suggest","提供休息建议")
        for i,title in enumerate(("少于 25 分钟","25 至不足 50 分钟","50 至不足 90 分钟","90 分钟及以上")):
            minutes("step"+str(i),title,value=profile.break_steps[i])
        minutes("reminder","温和休息提醒间隔",720,0)
        self.inputs["reminder"].setSpecialValueText("关闭")
        check("auto_long","专注到点进入休息")
        check("auto_next","休息结束自动开始下一轮")
        if profile.id=="pomo":
            self.inputs["short_on"].setEnabled(False)
            self.inputs["grouped"].setEnabled(False)
        self.visibility()
        self.error=label("","muted")
        self.error.hide()
        col.addWidget(self.error)
        row=box(horizontal=True)
        row.addWidget(button("恢复本模式默认",handler=self.reset_fields))
        row.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        col.addLayout(row)

    def visibility(self,*_):
        f=self.inputs
        if "auto_next" not in f: return
        up=f["count_up"].isChecked()
        short=self.custom or self.original.id=="pomo"
        micro=self.custom or self.original.id=="neuro"
        visible=dict(count_up=self.custom,focus=not up,short_on=short,short=short and f["short_on"].isChecked(),
            grouped=short,rounds=short and f["grouped"].isChecked(),micro_on=micro,
            suggest=up,reminder=up,auto_long=not up)
        for key in ("low","high","micro","inclusive"):
            visible[key]=micro and f["micro_on"].isChecked() and (key!="inclusive" or not up)
        for i in range(4): visible["step"+str(i)]=up and f["suggest"].isChecked()
        self.form.labelForField(f["long"]).setText("自主休息默认时长" if up else "长休息时长")
        if up and f["suggest"].isChecked(): visible["long"]=False
        for key,show in visible.items(): self.form.setRowVisible(f[key],show)

    def reset_fields(self):
        p=default(self.original.id,self.original.name)
        for k,w in self.inputs.items():
            v=p.break_steps[int(k[-1])] if k.startswith("step") else getattr(p,k)
            if isinstance(w,QCheckBox): w.setChecked(v)
            elif isinstance(w,QLineEdit): w.setText(v)
            else: w.setValue(v)

    def save(self):
        changes={}
        for key,w in self.inputs.items():
            if key.startswith("step"): continue
            changes[key]=(w.isChecked() if isinstance(w,QCheckBox) else
                          w.text().strip() if isinstance(w,QLineEdit) else w.value())
        changes["break_steps"]=tuple(self.inputs["step"+str(i)].value() for i in range(4))
        try: self.result_profile=replace(self.original,**changes)
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.accept()


class ModeChooser(QDialog):
    def __init__(self,w):
        super().__init__(w)
        self.w=w
        self.ctrl=w.ctrl
        self.setWindowTitle("选择专注模式")
        self.resize(460,420)
        col=box(self,margins=18,spacing=10)
        col.addWidget(label("下一轮使用的模式" if self.ctrl.sid else "专注模式","head"))
        self.list=QListWidget()
        self.list.setSpacing(3)
        c=w.dial.colors
        self.list.setStyleSheet(f"QListWidget {{background:{c['bg']};border:0;}} QListWidget::item {{padding:6px;border-radius:7px;}} QListWidget::item:selected {{background:{c['tint']};color:{c['ink']};}}")
        col.addWidget(self.list,1)
        row=box(horizontal=True)
        for title,fn in (("配置",self.edit),("新建模式",lambda:self.edit(True)),("删除",self.remove)):
            b=button(title,handler=lambda _,f=fn:f())
            row.addWidget(b)
            if title=="删除": self.delete=b
        row.addStretch()
        self.use=button("使用模式","primary",self.apply)
        row.addWidget(self.use)
        col.addLayout(row)
        self.list.currentRowChanged.connect(lambda _:self.delete.setEnabled(self.key() not in (*NAMES,None)))
        self.list.itemDoubleClicked.connect(lambda _:self.apply())
        self.refresh(self.ctrl.profiles.selected)

    def key(self):
        item=self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def refresh(self,selected):
        self.list.clear()
        for p in self.ctrl.profiles.items.values():
            current="   ✓" if self.ctrl.profiles.selected==p.id else ""
            text=f"{p.name}{current}\n{DESCRIPTIONS.get(p.id,'自定义方案')}   ·   {p.summary()}"
            item=QListWidgetItem(icon(ICONS.get(p.id,"settings"),self.w.dial.colors["accent"]),text)
            item.setData(Qt.UserRole,p.id)
            self.list.addItem(item)
            if p.id==selected: self.list.setCurrentItem(item)

    def edit(self,new=False):
        p=self.ctrl.profiles.create() if new else self.ctrl.profiles.items[self.key()]
        dialog=ProfileEditor(self,p)
        if dialog.exec():
            try: self.ctrl.save_profile(dialog.result_profile)
            except (ValueError,OSError,sqlite3.Error) as exc:
                QMessageBox.warning(self,"模式未保存",str(exc))
                return
            self.w.prefs.sync()
            self.refresh(p.id)
            self.w.render()

    def remove(self):
        key=self.key()
        if key in NAMES or key is None: return
        if QMessageBox.question(self,"删除自定义模式","删除这个方案？已保存的学习记录和运行中的计时会保留。")==QMessageBox.Yes:
            try: self.ctrl.profiles.delete(key)
            except sqlite3.Error as exc:
                QMessageBox.warning(self,"删除未完成",str(exc))
                return
            self.refresh(self.ctrl.profiles.selected)
            self.w.render()

    def apply(self):
        try: self.ctrl.profiles.select(self.key())
        except sqlite3.Error as exc:
            QMessageBox.warning(self,"模式未保存",str(exc))
            return
        self.w.render()
        self.accept()


class ModeStats(QWidget):
    def __init__(self,db):
        super().__init__()
        self.db=db
        col=box(self,margins=(0,8,0,0))
        row=box(horizontal=True)
        self.first=QDateEdit(QDate.currentDate().addDays(-29))
        self.last=QDateEdit(QDate.currentDate())
        self.range=QComboBox()
        self.range.addItems(["近 30 天","今天","全部","自定义"])
        row.addWidget(self.range)
        for w in (self.first,self.last):
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd")
            row.addWidget(w)
            w.dateChanged.connect(self.refresh)
        row.addStretch()
        col.addLayout(row)
        self.table=QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(["专注模式","实际学习","活动","使用轮数","轮次占比","每轮平均"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        col.addWidget(self.table)
        self.note=label("","muted")
        self.note.setWordWrap(True)
        col.addWidget(self.note)
        self.range.currentIndexChanged.connect(self.refresh)

    def refresh(self,*_):
        index=self.range.currentIndex()
        self.first.setVisible(index==3)
        self.last.setVisible(index==3)
        today=date.today()
        begin,end=((today-timedelta(days=29),today),(today,today),(date.min,date.max),
                   (self.first.date().toPython(),self.last.date().toPython()))[index]
        rows=mode_totals(self.db,begin,end) if begin<=end else []
        self.table.setRowCount(len(rows))
        uses=sum(r[4] for r in rows)
        for i,(_,name,ms,activities,cycles) in enumerate(rows):
            for j,v in enumerate((name,short_time(ms),activities,cycles,f"{cycles/uses:.0%}",short_time(ms//cycles))):
                self.table.setItem(i,j,QTableWidgetItem(str(v)))
        self.note.setText("请选择有效日期范围" if begin>end else "此范围没有学习活动" if not rows else
                "使用轮数按范围内有实际学习的会话去重。每轮平均仅计入所选日期内的有效学习时间。")
