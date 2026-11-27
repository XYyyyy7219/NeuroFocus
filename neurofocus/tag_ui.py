from datetime import date, datetime
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLineEdit, QColorDialog, QListWidget,
    QListWidgetItem, QMessageBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView)
from .widgets import box, button, label


def swatch(color):
    pix = QPixmap(13,13)
    pix.fill(QColor(color))
    return QIcon(pix)


def edit_tag(window, tag=None):
    dialog = QDialog(window)
    dialog.setWindowTitle("编辑学习标签" if tag else "新建学习标签")
    col = box(dialog,margins=18,spacing=12)
    col.addWidget(label("标签名称"))
    name = QLineEdit(tag.name if tag else "")
    col.addWidget(name)
    color = QColor(tag.color if tag else "#4B9173")
    pick = button("选择颜色")
    def choose():
        selected = QColorDialog.getColor(color, dialog, "标签颜色")
        if selected.isValid():
            color.setNamedColor(selected.name())
            pick.setIcon(swatch(color))
    pick.clicked.connect(choose)
    pick.setIcon(swatch(color))
    col.addWidget(pick)
    controls = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    controls.button(QDialogButtonBox.Save).setText("保存")
    controls.button(QDialogButtonBox.Cancel).setText("取消")
    col.addWidget(controls)
    result = []
    def save():
        try:
            result.append(window.ctrl.store.tags.save(name.text(),color.name(),tag.id if tag else None))
            dialog.accept()
        except (ValueError,sqlite3.Error) as exc:
            QMessageBox.warning(dialog,"无法保存标签",str(exc))
    controls.accepted.connect(save)
    controls.rejected.connect(dialog.reject)
    name.setFocus()
    return result[0] if dialog.exec() and result else None


class TagManager(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.w = window
        self.tags = window.ctrl.store.tags
        self.setWindowTitle("学习标签管理")
        self.resize(520,400)
        col = box(self,margins=16)
        self.list = QListWidget()
        col.addWidget(self.list)
        row = box(horizontal=True)
        for title,action in [("新建","new"),("编辑","edit"),("上移","up"),("下移","down"),
                             ("归档 / 恢复","archive"),("记录","detail")]:
            row.addWidget(button(title,handler=lambda _,a=action:self.act(a)))
        col.addLayout(row)
        self.reload(window.ctrl.tag_id)

    def reload(self,key):
        self.items = self.tags.all()
        self.list.clear()
        for i,t in enumerate(self.items):
            self.list.addItem(QListWidgetItem(swatch(t.color),t.name+("  ·  已归档" if t.archived else "")))
            if t.id == key: self.list.setCurrentRow(i)
        self.w.refresh_tags()

    def act(self,action):
        tag = self.items[self.list.currentRow()]
        key = tag.id
        try:
            if action == "new":
                key = edit_tag(self.w) or key
            elif action == "detail":
                self.w.advance("flush")
                start,end = self.tags.bounds("全部",date.today())
                show_detail(self.w,tag,start,end)
            elif not key:
                QMessageBox.information(self,"未分类","未分类用于保存没有选择标签的学习时间。")
            elif action == "edit":
                edit_tag(self.w,tag)
            elif action == "archive":
                if key == self.w.ctrl.tag_id:
                    self.w.change_tag(0)
                self.tags.archive(key,not tag.archived)
            elif not tag.archived:
                self.tags.move(key,-1 if action=="up" else 1)
        except (ValueError,sqlite3.Error) as exc:
            QMessageBox.warning(self,"标签管理",str(exc))
        self.reload(key)


def show_detail(window,tag,start,end):
    from .distribution import Trend, short_time
    dialog = QDialog(window)
    dialog.resize(620,510)
    dialog.setWindowTitle(tag.name+" · 学习记录")
    tags = window.ctrl.store.tags
    rows,daily,_ = tags.report(start,end)
    ms,share,average = next(((ms,p,a) for t,ms,p,a in rows if t.id==tag.id),(0,0,0))
    col = box(dialog,margins=16)
    title = label(tag.name,"head")
    title.setTextFormat(Qt.PlainText)
    col.addWidget(title)
    col.addWidget(label(f"{start} 至 {end}   ·   {short_time(ms)}   ·   占比 {share:.1%}   ·   日均 {short_time(average)}","muted"))
    trend = Trend()
    trend.set_data([r for r in daily if r[1]==tag.id],{tag.id:tag},start,end,window.ctrl.settings.dark)
    col.addWidget(trend)
    table = QTableWidget(0,4)
    table.setHorizontalHeaderLabels(["日期 / 周期","开始","结束","实际学习"])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().hide()
    col.addWidget(table)
    nav = box(horizontal=True)
    prev,next_ = button("上一页"),button("下一页")
    nav.addStretch()
    nav.addWidget(prev)
    nav.addWidget(next_)
    col.addLayout(nav)
    offset = 0
    def page(delta):
        nonlocal offset
        offset += delta
        records = tags.history(tag.id,start,end,26,offset)
        table.setRowCount(min(25,len(records)))
        fmt = lambda n: datetime.fromtimestamp(n/1000).strftime("%H:%M:%S") if n is not None else "旧版日汇总"
        for i,(day,sid,a,b,amount) in enumerate(records[:25]):
            for j,v in enumerate((f"{day} · {sid}",fmt(a),fmt(b),short_time(amount))):
                table.setItem(i,j,QTableWidgetItem(v))
        prev.setEnabled(offset>0)
        next_.setEnabled(len(records)>25)
    prev.clicked.connect(lambda:page(-25))
    next_.clicked.connect(lambda:page(25))
    page(0)
    dialog.exec()
