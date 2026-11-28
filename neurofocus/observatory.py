"""Immersive window overlay; the archive owns all data and filtering state."""
from html import escape
from PySide6.QtCore import Qt,QEvent,QTimer,QSignalBlocker,QRectF
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import (QWidget,QFrame,QLineEdit,QMenu,QDialog,QComboBox,QCheckBox,
    QDialogButtonBox,QListView,QTextBrowser)
from .widgets import box,label,button
from .reading_ui import Passage
from .distribution import short_time
from .history import wall_time
from .modes import snapshot_title

STYLE="""
QWidget#observatory {background:#080f1d;}
QWidget#observatory QLabel {background:transparent;color:#d9e5f2;}
QWidget#observatory QLabel#readingBody {font-size:15px;color:#e9ddc9;}
QWidget#observatory QLabel#readingCredit {font-size:10px;color:#afbacb;}
QWidget#observatory QToolButton#readingMenu {color:#b9cadb;background:transparent;}
QWidget#observatory QLabel[role="head"] {font-size:24px;font-weight:600;color:#f5eee4;}
QWidget#observatory QLabel[role="muted"] {color:#b9cadb;font-size:12px;}
QWidget#observatory QPushButton,QWidget#observatory QLineEdit {
    background:rgba(17,29,46,213);color:#e4eaf1;border:1px solid #394555;
    border-radius:12px;padding:6px 12px;font-size:12px;}
QWidget#observatory QPushButton:hover {background:#26394b;border-color:#a69378;}
QFrame#skyPanel,QFrame#skyTime {background:rgba(13,23,38,232);border:1px solid #465264;border-radius:14px;}
QWidget#observatory QListView {background:#121d2b;color:#dce6ed;border:0;selection-background-color:#324454;}
QWidget#observatory QSlider::groove:horizontal {height:3px;background:#3f4c5a;}
QWidget#observatory QSlider::handle:horizontal {width:10px;margin:-4px 0;background:#edcc97;border-radius:5px;}
"""


class Observatory(QWidget):
    def __init__(self,h):
        super().__init__(h.w.centralWidget())
        self.h=h
        self.host=self.parentWidget()
        self.host.installEventFilter(self)
        self.setObjectName("observatory")
        self.setStyleSheet(STYLE)
        self.hide()
        self.full_before=None
        self.detail_key=None
        self.clean=False
        self.sky=h.sky
        self.sky.setParent(self)
        self.sky.set_low(h.w.ctrl.settings.sky_low_motion)
        self.top=QWidget(self)
        top=box(self.top,horizontal=True,spacing=6)
        top.addWidget(button("‹  学习档案",handler=self.leave))
        self.passage=Passage(h.w,sky=True)
        top.addWidget(self.passage,1)
        top.addStretch(0)
        self.search=QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(205)
        self.search.setPlaceholderText("搜索主题或学习日志")
        top.addWidget(self.search)
        self.filter_btn=button("筛选",handler=self.filters)
        top.addWidget(self.filter_btn)
        self.results_btn=button("记录",handler=self.toggle_results)
        top.addWidget(self.results_btn)
        more=button("···")
        more.setAccessibleName("星图显示选项")
        self.menu=QMenu(more)
        self.menu.addAction("全屏探索  F11",self.fullscreen)
        self.menu.addAction("纯净观测  F9",self.toggle_clean)
        self.menu.addAction("保存当前视野 PNG",h.export_sky)
        for name,initial,fn in (("按时长调整恒星大小",True,h.set_sizes),
                                ("低负载 · 关闭镜头动画",self.sky.low,self.low_motion)):
            action=self.menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(initial)
            action.toggled.connect(fn)
        more.setMenu(self.menu)
        top.addWidget(more)
        self.heading=QWidget(self)
        self.heading.setAttribute(Qt.WA_TransparentForMouseEvents)
        col=box(self.heading,spacing=3)
        self.title=label("学习宇宙","head")
        self.title.setTextFormat(Qt.PlainText)
        self.sub=label("","muted")
        self.sub.setTextFormat(Qt.PlainText)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        self.nav=QWidget(self)
        row=box(self.nav,horizontal=True)
        row.addWidget(button("全景",handler=lambda:self.sky.enter(())))
        self.up=button("上一级",handler=self.sky.ascend)
        row.addWidget(self.up)
        self.time=QFrame(self)
        self.time.setObjectName("skyTime")
        row=box(self.time,horizontal=True,margins=(10,6,12,6))
        row.addWidget(h.play)
        row.addWidget(h.slide,1)
        row.addWidget(h.cutoff)
        self.legend=label("亮点 · 学习活动     云气 · 背景尘埃","muted")
        self.legend.setParent(self)
        self.legend.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.panel=QFrame(self)
        self.panel.setObjectName("skyPanel")
        col=box(self.panel,margins=15,spacing=8)
        row=box(horizontal=True)
        self.panel_title=label("活动记录")
        row.addWidget(self.panel_title,1)
        row.addWidget(button("收起",handler=self.panel.hide))
        col.addLayout(row)
        self.matches=QListView()
        self.matches.setModel(h.model)
        self.matches.setUniformItemSizes(True)
        col.addWidget(self.matches)
        self.note=QTextBrowser()
        self.note.setOpenLinks(False)
        self.note.setStyleSheet("QTextBrowser {color:#e1e7ed; background:transparent;border:0;font-size:13px;}")
        self.sky.obstacles=self.obstacles
        col.addWidget(self.note)
        row=box(horizontal=True,spacing=4)
        self.links=QWidget()
        self.links.setLayout(row)
        for name,fn in (("日志",h.edit),("过程",h.detail),("时间轴",h.jump_time)):
            row.addWidget(button(name,handler=fn))
        col.addWidget(self.links)
        self.panel.hide()
        self.matches.clicked.connect(h.from_list)
        self.matches.activated.connect(h.from_list)
        self.sky.picked.connect(self.show_detail)
        self.search_timer=QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(230)
        self.search_timer.timeout.connect(self.apply_search)
        self.search.textEdited.connect(lambda _:self.search_timer.start())
        self.search.returnPressed.connect(lambda:self.apply_search(True))
        for seq,fn in (("F9",self.toggle_clean),("Esc",self.escape),("F11",self.fullscreen),("Ctrl+F",self.search.setFocus)):
            key=QShortcut(QKeySequence(seq),self)
            key.setContext(Qt.WidgetWithChildrenShortcut)
            key.activated.connect(fn)

    def eventFilter(self,obj,e):
        if obj is self.host and e.type()==QEvent.Resize:
            self.setGeometry(obj.rect())
        return super().eventFilter(obj,e)

    def resizeEvent(self,e):
        super().resizeEvent(e)
        w,h=self.width(),self.height()
        self.sky.setGeometry(self.rect())
        self.top.setGeometry(22,16,w-44,43)
        self.heading.setGeometry(27,67,min(390,w-215),64)
        self.nav.setGeometry(max(25,w-170),68,145,34)
        self.legend.setGeometry(26,h-38,275,23)
        width=min(500,max(255,w-340))
        self.time.setGeometry(w-width-22,h-60,width,44)
        self.position_panel()

    def position_panel(self):
        w,h=self.width(),self.height()
        wide=min(340,round(w*.36))
        height=min(440,h-215) if self.sky.observing else min(225,h-200)
        self.panel.setGeometry(w-wide-22,max(133,(h-height)//2),wide,max(136,height))

    def obstacles(self):
        if self.clean: return []
        return [QRectF(w.geometry()).adjusted(-4,-3,4,3)
                for w in (self.top,self.nav,self.heading,self.time,self.legend,self.panel) if w.isVisible()]

    def toggle_clean(self):
        if not self.clean: self.restore_panel=self.panel.isVisible()
        self.clean=not self.clean
        self.sky.show_labels=not self.clean
        for w in (self.top,self.heading,self.time,self.legend): w.setVisible(not self.clean)
        self.nav.setVisible(not self.clean and bool(self.sky.scope))
        self.panel.setVisible(not self.clean and self.restore_panel and (self.sky.observing is not None or not self.matches.isHidden()))
        self.sky.viewport().update()

    def open_view(self):
        if self.isHidden():
            self.setGeometry(self.host.rect())
            self.show()
            self.raise_()
            self.sky.setFocus()
            self.h.w.reading_refresh(force=True)
        if not self.search_timer.isActive(): self.search.setText(self.h.query.text())
        self.filter_btn.setText("已筛选" if self.h.tag.currentData() is not None or self.h.range_on.isChecked() else "筛选")

    def close_view(self):
        if self.clean: self.toggle_clean()
        self.search_timer.stop()
        self.panel.hide()
        self.detail_key=None
        if self.full_before is not None: self.fullscreen()
        self.hide()

    def leave(self):
        self.h.tabs.setCurrentIndex(0)

    def escape(self):
        if self.clean: self.toggle_clean()
        elif self.sky.observing: self.sky.ascend()
        elif self.panel.isVisible(): self.panel.hide()
        elif self.full_before is not None: self.fullscreen()
        elif self.sky.scope: self.sky.ascend()
        else: self.leave()

    def fullscreen(self):
        w=self.h.w
        if self.full_before is None:
            self.full_before=w.isMaximized()
            w.showFullScreen()
        else:
            maxi,self.full_before=self.full_before,None
            w.showMaximized() if maxi else w.showNormal()

    def low_motion(self,value):
        self.h.w.configure(sky_low_motion=value)
        self.sky.set_low(self.h.w.ctrl.settings.sky_low_motion)

    def filters(self):
        h=self.h
        d=QDialog(self)
        d.setWindowTitle("筛选学习宇宙")
        col=box(d,margins=18)
        tags=QComboBox()
        for i in range(h.tag.count()): tags.addItem(h.tag.itemText(i),h.tag.itemData(i))
        tags.setCurrentIndex(h.tag.currentIndex())
        col.addWidget(label("学科"))
        col.addWidget(tags)
        dates=QCheckBox("限定活动日期")
        dates.setChecked(h.range_on.isChecked())
        col.addWidget(dates)
        first,last=(h.date_edit(edit.date().toPython()) for edit in (h.first,h.last))
        for edit in (first,last):
            col.addWidget(edit)
            edit.setEnabled(dates.isChecked())
            dates.toggled.connect(edit.setEnabled)
        msg=label("","muted")
        col.addWidget(msg)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(lambda:msg.setText("开始日期须早于或等于结束日期") if dates.isChecked() and first.date()>last.date() else d.accept())
        buttons.rejected.connect(d.reject)
        col.addWidget(buttons)
        if d.exec():
            for dest,setter,val in ((h.tag,"setCurrentIndex",tags.currentIndex()),(h.range_on,"setChecked",dates.isChecked()),
                                    (h.first,"setDate",first.date()),(h.last,"setDate",last.date())):
                with QSignalBlocker(dest): getattr(dest,setter)(val)
            self.sky.scope=()
            self.sky.observing=None
            h.filter_rows()
            self.sky.frame_scene(True)

    def apply_search(self,first=False):
        self.search_timer.stop()
        self.sky.scope=()
        self.sky.observing=None
        with QSignalBlocker(self.h.query): self.h.query.setText(self.search.text())
        self.h.filter_rows()
        if self.search.text().strip() and self.h.model.rowCount():
            if first or self.h.model.rowCount()==1:
                a=self.h.model.rows[0]
                self.sky.enter((a.tag,a.note[0].strip(),a.key))
            else:
                self.sky.frame_scene(True)
                self.show_results()
        else:
            self.panel.hide()
            self.sky.frame_scene(True)

    def toggle_results(self):
        if self.panel.isVisible() and self.matches.isVisible(): self.panel.hide()
        else: self.show_results()

    def show_results(self):
        self.detail_key=None
        self.panel_title.setText(f"活动记录 · {self.h.model.rowCount()}")
        self.matches.show()
        self.note.hide()
        self.links.hide()
        self.panel.show()

    def show_detail(self,key):
        self.detail_key=key
        self.h.select(key)
        a=self.h.items.get(key)
        if a is None: return
        self.position_panel()
        self.panel_title.setText("恒星观测   /   学习活动")
        self.matches.hide()
        sid=a.key[0]
        row=self.h.db.execute("SELECT config FROM session_protocol WHERE sid=?",(sid,)).fetchone()
        micro=self.h.db.execute("SELECT sum(micro_count),sum(micro) FROM days WHERE sid=?",(sid,)).fetchone()
        protocol=escape(snapshot_title(row[0] if row else None))
        rests=dict(self.h.db.execute("SELECT kind,sum(ms) FROM rest_days WHERE sid=? GROUP BY kind",(sid,)))
        def safe(value): return escape(str(value)).replace("\n","<br>")
        tag=self.h.tags[a.tag].name
        parts=[f"<h3>{safe(a.note[0] or tag)}</h3>",
               f"<p>{safe(tag)}　·　{a.day}<br>{wall_time(a.started)} — {wall_time(a.ended)}</p>",
               f"<p>实际学习　<b>{short_time(a.ms)}</b><br>周期策略　{protocol}<br>周期微休息　{micro[0] or 0} 次 · {short_time(micro[1] or 0)}</p>"]
        if rests: parts.append(f"<p>周期短休息　{short_time(rests.get('short',0))}<br>周期自主休息　{short_time(rests.get('manual',0))}</p>")
        for name,value in zip(("学习收获","疑问与思考","下一步","学习体验"),a.note[1:]):
            if value: parts.append(f"<p><b>{name}</b><br>{safe(value)}</p>")
        if not any(a.note): parts.append("<p>可在「日志」中为这次学习补记一句话。</p>")
        html="".join(parts)
        if html!=getattr(self,"_html",None):
            self._html=html
            self.note.setHtml(html)
        self.note.show()
        self.links.show()
        self.panel.setVisible(not self.clean)

    def sync(self,rows):
        h=self.h
        scope=self.sky.scope
        self.title.setText(("学习宇宙" if not scope else h.tags[scope[0]].name if len(scope)==1 else scope[1] or "未填写主题")[:44])
        suffix=f"{len(rows)} 次活动   ·   {short_time(sum(a.ms for a in rows))}"
        if not scope: suffix=f"{len(self.sky.nodes)} 个学科星系   /   "+suffix
        elif len(scope)==2: suffix=h.tags[scope[0]].name+"   /   "+suffix
        if self.sky.observing:
            self.title.setText("恒星观测")
            suffix="宇宙  ›  "+h.tags[scope[0]].name+"  ›  "+(scope[1] or "未填写主题")
        self.sub.setText(suffix)
        self.up.setText("返回星团" if self.sky.observing else "上一级")
        self.nav.setVisible(bool(scope) and not self.clean)
        if self.detail_key and self.detail_key!=self.sky.observing:
            self.detail_key=None
            self.panel.hide()
        dense=any(node.count>160 for node in self.sky.nodes.values())
        self.legend.setText("高密度星系 · 每组最多显示 160 条活动" if dense else
                            "亮点 · 学习活动     弧光 · 已写日志" if len(scope)==2 else
                            "亮点 · 学习活动     云气 · 背景尘埃")
        h.play.setEnabled(h.slide.maximum()>0)
        if self.panel.isVisible():
            if self.detail_key and self.detail_key==self.sky.selected and any(a.key==self.detail_key for a in rows) and len(scope)==2:
                self.show_detail(self.detail_key)
            elif self.matches.isVisible(): self.panel_title.setText(f"活动记录 · {len(rows)}")
            else: self.panel.hide()
