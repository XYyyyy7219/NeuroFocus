from datetime import date,timedelta
from pathlib import Path
from PySide6.QtCore import Qt,QDate,QTimer,QSignalBlocker
from PySide6.QtWidgets import (QWidget,QComboBox,QDateEdit,QLineEdit,QListView,QStackedWidget,
    QSlider,QCheckBox,QDialog,QPlainTextEdit,QFileDialog,QMessageBox,QTabBar)
from .archive_widgets import ActivityList,JournalEditor,Timeline
from .history import activities,markdown,save_note,session_detail,wall_time,TITLES
from .universe import Sky,layout_slots
from .distribution import short_time
from .observatory import Observatory
from .widgets import box,label,button


class Archive(QWidget):
    def __init__(self,w):
        super().__init__()
        self.w=w
        self.db=w.ctrl.store.db
        self.version=None
        self.items={}
        self.tags={}
        self.current=None
        self.slots={}
        self.loading=True
        col=box(self,spacing=7)
        self.tabs=QTabBar()
        for title in ("学习时间轴","学习日志","学习星图"): self.tabs.addTab(title)
        col.addWidget(self.tabs)
        row=box(horizontal=True)
        self.tag=QComboBox()
        self.tag.setMaximumWidth(145)
        self.query=QLineEdit()
        self.query.setPlaceholderText("搜索主题、收获、疑问或下一步")
        self.query.setClearButtonEnabled(True)
        row.addWidget(self.tag)
        row.addWidget(self.query,1)
        col.addLayout(row)
        self.datebar=QWidget()
        row=box(self.datebar,horizontal=True)
        self.mode=QComboBox()
        self.mode.addItems(["日视图","周视图"])
        self.day=self.date_edit(date.today())
        row.addWidget(self.mode)
        row.addWidget(button("‹",handler=lambda:self.move_day(-1)))
        row.addWidget(self.day)
        row.addWidget(button("›",handler=lambda:self.move_day(1)))
        row.addWidget(button("今天",handler=lambda:self.day.setDate(QDate.currentDate())))
        row.addStretch()
        col.addWidget(self.datebar)
        self.periodbar=QWidget()
        row=box(self.periodbar,horizontal=True)
        self.range_on=QCheckBox("日期范围")
        self.first=self.date_edit(date(date.today().year,1,1))
        self.last=self.date_edit(date.today())
        for item in (self.range_on,self.first,label("至"),self.last): row.addWidget(item)
        row.addStretch()
        col.addWidget(self.periodbar)
        self.timeline=Timeline()
        self.sky=Sky()
        self.timeline.picked.connect(self.select)
        self.sky.picked.connect(self.select)
        self.sky.changed.connect(self.breadcrumb)
        col.addWidget(self.timeline,3)
        self.play=button("播放演化",handler=self.playback)
        self.slide=QSlider(Qt.Horizontal)
        self.cutoff=label("","muted")
        self.list=QListView()
        self.list.setUniformItemSizes(True)
        self.model=ActivityList()
        self.list.setModel(self.model)
        self.list.clicked.connect(lambda i:self.from_list(i))
        self.list.activated.connect(lambda i:self.from_list(i))
        self.list.selectionModel().currentChanged.connect(lambda i,_:self.select(self.model.rows[i.row()].key) if i.isValid() else None)
        col.addWidget(self.list,1)
        self.info=label("","muted")
        self.info.setTextFormat(Qt.PlainText)
        self.info.setWordWrap(True)
        col.addWidget(self.info)
        row=box(horizontal=True,spacing=4)
        self.actions=[]
        for title,handler in (("日志",self.edit),("过程详情",self.detail),("时间轴",self.jump_time),
                              ("定位恒星",self.jump_sky),("导出 .md",self.export_note),("删除日志",self.delete_note)):
            b=button(title,handler=handler)
            self.actions.append(b)
            row.addWidget(b)
        row.addStretch()
        col.addLayout(row)
        self.ticker=QTimer(self)
        self.ticker.setInterval(220)
        self.ticker.timeout.connect(self.step)
        self.slide.valueChanged.connect(self.draw_sky)
        for sig in (self.tag.currentIndexChanged,self.query.textChanged,self.mode.currentIndexChanged,
                    self.day.dateChanged,self.range_on.toggled,self.first.dateChanged,self.last.dateChanged,
                    self.tabs.currentChanged): sig.connect(self.filter_rows)
        self.stage=Observatory(self)
        self.loading=False

    @staticmethod
    def date_edit(d):
        field=QDateEdit(d)
        field.setCalendarPopup(True)
        field.setDisplayFormat("yyyy-MM-dd")
        return field

    def refresh(self,force=False):
        version=self.db.total_changes
        if not force and self.version==version: return
        self.version=version
        rows=activities(self.db)
        self.items={a.key:a for a in rows}
        self.slots=layout_slots(rows)
        self.tags={t.id:t for t in self.w.ctrl.store.tags.all()}
        with QSignalBlocker(self.tag):
            old=self.tag.currentData()
            self.tag.clear()
            self.tag.addItem("全部标签",None)
            for t in self.tags.values(): self.tag.addItem(t.name+(" · 已归档" if t.archived else ""),t.id)
            self.tag.setCurrentIndex(max(0,self.tag.findData(old)) if old is not None else 0)
        self.filter_rows(keep_playing=True)

    def filter_rows(self,*_,keep_playing=False):
        if self.loading or self.version is None: return
        tab=self.tabs.currentIndex()
        timeline,journal,sky=tab==0,tab==1,tab==2
        self.datebar.setVisible(timeline)
        self.periodbar.setVisible(not timeline)
        if sky: self.stage.open_view()
        elif not self.stage.isHidden(): self.stage.close_view()
        self.timeline.setVisible(timeline)
        self.actions[2].setVisible(not timeline)
        self.actions[3].setVisible(not sky)
        for b in self.actions[4:]: b.setVisible(journal)
        self.first.setEnabled(self.range_on.isChecked())
        self.last.setEnabled(self.range_on.isChecked())
        if not keep_playing or not sky:
            self.ticker.stop()
            self.play.setText("播放演化")
        start=self.day.date().toPython()
        n=7 if self.mode.currentIndex() else 1
        if n==7: start-=timedelta(days=start.weekday())
        if timeline: low,high=str(start),str(start+timedelta(days=n-1))
        elif self.range_on.isChecked(): low,high=self.first.date().toString(Qt.ISODate),self.last.date().toString(Qt.ISODate)
        else: low,high="","9999-12-31"
        tag=self.tag.currentData()
        q=self.query.text().strip()
        rows=[a for a in self.items.values() if low<=a.day<=high and (tag is None or tag==a.tag)
              and (a.matches(q) or q.casefold() in self.tags[a.tag].name.casefold()) and (not journal or any(a.note))]
        if timeline: self.timeline.render_rows(rows,self.tags,start,n)
        if sky:
            self.sky_rows=rows
            prev_cut=self.cutoff.text()
            at_end=self.slide.value()==self.slide.maximum()
            self.min_day=date.fromisoformat(min((a.day for a in rows),default=str(date.today())))
            self.max_day=date.fromisoformat(max((a.day for a in rows),default=str(self.min_day)))
            with QSignalBlocker(self.slide):
                self.slide.setRange(0,(self.max_day-self.min_day).days)
                v=(date.fromisoformat(prev_cut)-self.min_day).days if prev_cut and not at_end else self.slide.maximum()
                self.slide.setValue(v)
            self.draw_sky()
        else: self.list_rows(rows)

    def list_rows(self,rows):
        prev=self.current
        self.model.replace(sorted(rows,key=lambda a:(a.day,a.started or 0,a.key),reverse=True),self.tags)
        visible={a.key for a in rows}
        self.select(prev if prev in visible else self.model.rows[0].key if rows else None)
        if not rows:
            self.info.setText("当前范围没有匹配的记录。可在时间轴选择活动补写日志。" if self.tabs.currentIndex()==1 else "当前范围没有匹配的学习活动。")

    def select(self,key):
        self.current=key
        a=self.items.get(key)
        for b in self.actions: b.setEnabled(a is not None)
        if a:
            title=a.note[0] or self.tags[a.tag].name
            text=f"{title}　·　{a.day}　{wall_time(a.started)}–{wall_time(a.ended)}　·　实际 {short_time(a.ms)}"
            self.info.setText(text+("\n"+a.note[1][:100] if a.note[1] else ""))
        else: self.info.clear()

    def from_list(self,index):
        a=self.model.rows[index.row()]
        self.select(a.key)
        if self.tabs.currentIndex()==2: self.sky.enter((a.tag,a.note[0].strip(),a.key))

    def move_day(self,amount):
        self.day.setDate(self.day.date().addDays(amount*(7 if self.mode.currentIndex() else 1)))

    def open_day(self,d):
        self.w.navigate(3)
        self.tabs.setCurrentIndex(0)
        self.query.clear()
        self.tag.setCurrentIndex(0)
        self.mode.setCurrentIndex(0)
        self.day.setDate(d)
        self.filter_rows()

    def jump_time(self):
        a=self.items[self.current]
        self.open_day(date.fromisoformat(a.day))
        self.select(a.key)

    def jump_sky(self):
        a=self.items[self.current]
        self.query.clear()
        self.tag.setCurrentIndex(0)
        self.range_on.setChecked(False)
        self.tabs.setCurrentIndex(2)
        self.slide.setValue(self.slide.maximum())
        self.sky.enter((a.tag,a.note[0].strip(),a.key))

    def draw_sky(self,*_):
        if self.tabs.currentIndex()!=2 or not hasattr(self,"min_day"): return
        cutoff=str(self.min_day+timedelta(days=self.slide.value()))
        self.cutoff.setText(cutoff)
        rows=[a for a in self.sky_rows if a.day<=cutoff]
        self.cut_rows=rows
        active=self.items.get(self.sky.observing)
        if active and (active.tag,active.note[0].strip())!=self.sky.scope and active in rows:
            path=(active.tag,active.note[0].strip(),active.key)
            self.sky.scope=()
            self.sky.populate(rows,self.tags,self.slots)
            self.sky.enter(path)
            return
        if self.sky.scope and not any((a.tag,a.note[0].strip())[:len(self.sky.scope)]==self.sky.scope for a in rows):
            self.sky.scope=()
        self.sky.populate(rows,self.tags,self.slots)

    def breadcrumb(self):
        path=self.sky.scope
        if hasattr(self,"cut_rows"):
            rows=[a for a in self.cut_rows if (a.tag,a.note[0].strip())[:len(path)]==path]
            self.list_rows(rows)
            self.stage.sync(rows)

    def set_sizes(self,value):
        self.sky.weighted=value
        self.sky.rebuild(False)

    def playback(self):
        if self.ticker.isActive():
            self.ticker.stop()
            self.play.setText("播放演化")
        else:
            if self.slide.value()==self.slide.maximum(): self.slide.setValue(0)
            self.ticker.start()
            self.play.setText("暂停")
    def step(self):
        if self.slide.value()>=self.slide.maximum(): self.playback()
        else: self.slide.setValue(self.slide.value()+1)

    def hideEvent(self,event):
        self.ticker.stop()
        self.play.setText("播放演化")
        super().hideEvent(event)

    def edit(self):
        a=self.items.get(self.current)
        if a:
            JournalEditor(self,self.db,a,self.tags[a.tag].name).exec()
            self.refresh(True)

    def detail(self):
        a=self.items[self.current]
        dialog=QDialog(self)
        dialog.setWindowTitle("学习过程")
        dialog.resize(570,500)
        col=box(dialog,margins=14)
        text=QPlainTextEdit(session_detail(self.db,a)+"\n\n"+markdown(a,self.tags[a.tag].name))
        text.setReadOnly(True)
        col.addWidget(text)
        col.addWidget(button("关闭",handler=dialog.accept))
        dialog.exec()

    def delete_note(self):
        if QMessageBox.question(self,"删除日志","删除此活动的日志文字？学习时长将保留。")!=QMessageBox.Yes: return
        save_note(self.db,self.current,("",)*5)
        self.refresh(True)

    def export_note(self):
        a=self.items[self.current]
        path,_=QFileDialog.getSaveFileName(self,"导出学习日志",a.day+".md","Markdown (*.md)")
        if path:
            try: Path(path).write_text(markdown(a,self.tags[a.tag].name),encoding="utf-8")
            except OSError as exc: QMessageBox.warning(self,"导出失败",str(exc))

    def export_sky(self):
        path,_=QFileDialog.getSaveFileName(self,"导出当前视野","学习星图.png","PNG (*.png)")
        if path and not self.sky.export(path): QMessageBox.warning(self,"导出失败","请检查保存位置。")
