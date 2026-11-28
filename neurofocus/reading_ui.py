"""Reading surfaces for the timer and observatory, plus the local collection editor."""
from pathlib import Path
from PySide6.QtCore import Qt, QEvent, QSignalBlocker
from PySide6.QtGui import QTextLayout, QTextOption
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
    QSizePolicy, QSplitter, QToolButton, QWidget)
from .literature import Entry, excerpt_lines, read_json
from .widgets import box, button, label


class PassageLabel(QLabel):
    """Measure line breaks after font or viewport changes, with a bounded preview height."""
    def __init__(self, lines=2):
        super().__init__()
        self.lines = lines
        self.full = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

    def compose(self):
        width = max(1, self.width())
        flat = " ".join(self.full.split())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout = QTextLayout(flat, self.font())
        layout.setTextOption(option)
        layout.beginLayout()
        parts = []
        # Qt layout offsets count UTF-16 code units, including both halves of emoji.
        data = flat.encode("utf-16-le")
        for i in range(self.lines):
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            start = 2 * line.textStart()
            end = start + 2 * line.textLength()
            if i+1 == self.lines and end < len(data):
                parts.append(self.fontMetrics().elidedText(data[start:].decode("utf-16-le"), Qt.TextElideMode.ElideRight, width))
            else:
                parts.append(data[start:end].decode("utf-16-le").rstrip())
        layout.endLayout()
        self.setText("\n".join(parts))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.compose()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.FontChange and hasattr(self,"full"):
            self.compose()

    def display(self, value):
        self.full = value
        self.setAccessibleName(value)
        self.compose()


class Passage(QWidget):
    def __init__(self, window, sky=False):
        super().__init__()
        self.host, self.sky = window, sky
        self.entry: Entry | None = None
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = box(self, horizontal=True, margins=(10,0,2,0) if not sky else (8,0,8,0), spacing=5)
        col = box(spacing=0)
        self.words = PassageLabel(1 if sky else 2)
        self.words.setObjectName("readingBody")
        self.source = PassageLabel(1)
        self.source.setObjectName("readingCredit")
        col.addWidget(self.words)
        col.addWidget(self.source)
        row.addLayout(col, 1)
        self.more = QToolButton()
        self.more.setText("···")
        self.more.setObjectName("readingMenu")
        self.more.setAccessibleName("文案选项")
        self.more.setToolTip("阅读全文、收藏或换一则")
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self.more)
        self.menu.addAction("阅读全文", self.read)
        self.next = self.menu.addAction("换一则", lambda:window.reading_refresh(another="starMap" if sky else "home"))
        self.star = self.menu.addAction("收藏", self.favorite)
        self.menu.aboutToShow.connect(self.prepare_menu)
        self.more.setMenu(self.menu)
        row.addWidget(self.more)
        self.hide()

    def prepare_menu(self):
        if self.entry:
            self.star.setText("取消收藏" if self.entry.favorite else "收藏")
        self.next.setEnabled(self.host.ctrl.sid is None)

    def favorite(self):
        if self.entry:
            try:
                self.host.library.edit(self.entry.id, favorite=not self.entry.favorite)
                self.host.reading_refresh(force=True)
            except (ValueError,OSError) as exc:
                QMessageBox.warning(self,"收藏未保存",str(exc))

    def read(self):
        if not self.entry:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.entry.title)
        col = box(dialog, margins=22, spacing=12)
        content = QPlainTextEdit(self.entry.text or "")
        content.setReadOnly(True)
        col.addWidget(content)
        credit = label(self.entry.source.credit(True), "muted")
        credit.setTextFormat(Qt.TextFormat.PlainText)
        credit.setWordWrap(True)
        col.addWidget(credit)
        col.addWidget(button("合上",handler=dialog.accept),0,Qt.AlignmentFlag.AlignRight)
        dialog.resize(510,290)
        dialog.exec()

    def present(self, item):
        if item != self.entry:
            self.entry = item
            self.words.display((item.text or "") if item else "")
            self.source.display(item.source.credit() if item else "")
        self.setVisible(item is not None)


class Collection(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.w, self.lib = window, window.library
        self.setWindowTitle("文学文案库")
        self.resize(770,480)
        col = box(self, margins=16, spacing=10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索主题、作品、卷、类别或标签")
        self.search.setAccessibleName("检索文案")
        tools = box(horizontal=True)
        tools.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItems(["全部条目","已收藏","已启用","待选摘录"])
        tools.addWidget(self.filter)
        col.addLayout(tools)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        split.addWidget(self.list)
        pane = QWidget()
        fields = box(pane, margins=(10,0,0,0), spacing=8)
        self.title = label("", "head")
        self.credit = label("", "muted")
        self.meta = label("", "muted")
        for line in (self.title,self.credit,self.meta):
            line.setTextFormat(Qt.TextFormat.PlainText)
            line.setWordWrap(True)
            fields.addWidget(line)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        fields.addWidget(self.preview, 1)
        flags = box(horizontal=True)
        self.enabled = QCheckBox("启用")
        self.favorite = QCheckBox("收藏")
        self.edit = button("填写摘录",handler=self.edit_text)
        for widget in (self.enabled,self.favorite,self.edit):
            flags.addWidget(widget)
        flags.addStretch()
        fields.addLayout(flags)
        split.addWidget(pane)
        split.setSizes([245,465])
        col.addWidget(split, 1)
        actions = box(horizontal=True)
        actions.addWidget(button("导入 JSON",handler=self.import_file))
        actions.addWidget(button("导出文案库",handler=self.export_file))
        actions.addStretch()
        actions.addWidget(button("完成",handler=self.accept))
        col.addLayout(actions)
        self.message = label(self.lib.problem, "muted")
        self.message.setWordWrap(True)
        self.message.setVisible(bool(self.lib.problem))
        col.addWidget(self.message)
        self.list.currentItemChanged.connect(self.detail)
        self.search.textChanged.connect(self.rebuild)
        self.filter.currentIndexChanged.connect(self.rebuild)
        self.enabled.toggled.connect(lambda v:self.change(enabled=v))
        self.favorite.toggled.connect(lambda v:self.change(favorite=v))
        self.rebuild()

    def current(self):
        row = self.list.currentItem()
        return self.lib.entries.get(row.data(Qt.ItemDataRole.UserRole)) if row else None

    def rebuild(self,*_):
        current = self.current()
        words = self.search.text().casefold().split()
        mode = self.filter.currentIndex()
        with QSignalBlocker(self.list):
            self.list.clear()
            selected = 0
            for e in self.lib.entries.values():
                hay = " ".join((e.id,e.title,e.source.credit(True),*e.categories,*e.tags)).casefold()
                if not all(term in hay for term in words):
                    continue
                if (mode==1 and not e.favorite) or (mode==2 and not e.enabled) or (mode==3 and e.text):
                    continue
                row = QListWidgetItem(("☆  " if e.favorite else "")+e.title)
                row.setData(Qt.ItemDataRole.UserRole,e.id)
                if current and current.id==e.id:
                    selected = self.list.count()
                self.list.addItem(row)
            self.list.setCurrentRow(selected)
        self.detail()

    def detail(self,*_):
        e = self.current()
        self.title.setText(e.title if e else "没有匹配的文案")
        self.credit.setText(e.source.credit(True) if e else "")
        self.meta.setText("　".join((*e.categories,*e.tags)) if e else "")
        body = (e.text or "此项仅保留索引。可在本机填写有权使用的摘录。") if e else ""
        self.preview.setPlainText(body)
        with QSignalBlocker(self.enabled), QSignalBlocker(self.favorite):
            self.enabled.setChecked(bool(e and e.enabled))
            self.favorite.setChecked(bool(e and e.favorite))
        self.enabled.setEnabled(bool(e and e.text))
        self.favorite.setEnabled(e is not None)
        self.edit.setEnabled(bool(e and (e.id not in self.lib.base or not self.lib.base[e.id].text)))

    def change(self,**changes):
        e = self.current()
        if e:
            try:
                self.lib.edit(e.id,**changes)
                self.w.reading_refresh(force=True)
            except (ValueError,OSError) as exc:
                QMessageBox.warning(self,"文案未保存",str(exc))
            self.rebuild()

    def edit_text(self):
        e = self.current()
        if not e:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("本地摘录 · "+e.title)
        col = box(dialog,margins=16)
        hint = label(e.source.credit(True),"muted")
        hint.setTextFormat(Qt.TextFormat.PlainText)
        hint.setWordWrap(True)
        col.addWidget(hint)
        editor = QPlainTextEdit(e.text or "")
        editor.setPlaceholderText("填写自己有权使用的文字。保存后可在对应场景展示。")
        col.addWidget(editor)
        if e.source.lineStart:
            def select_txt():
                path,_ = QFileDialog.getOpenFileName(dialog,"选择此版本的本地文本","","文本 (*.txt)")
                if not path:
                    return
                try:
                    passage = excerpt_lines(Path(path),e.source)
                except (OSError,ValueError) as exc:
                    QMessageBox.warning(dialog,"无法读取行段",str(exc))
                    return
                selector = QDialog(dialog)
                selector.setWindowTitle("核对版本并选中文字")
                layout = box(selector,margins=16)
                layout.addWidget(label("核对章节后，拖选想保留的文字。", "muted"))
                original = QPlainTextEdit(passage)
                original.setReadOnly(True)
                layout.addWidget(original)
                use = button("使用所选文字",handler=selector.accept)
                use.setEnabled(False)
                original.copyAvailable.connect(use.setEnabled)
                layout.addWidget(use)
                selector.resize(550,360)
                if selector.exec():
                    editor.setPlainText(original.textCursor().selectedText().replace("\u2029","\n"))
            col.addWidget(button("从 TXT 选取此行段…",handler=select_txt),0,Qt.AlignmentFlag.AlignLeft)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        col.addWidget(buttons)
        dialog.resize(500,320)
        if dialog.exec():
            body = editor.toPlainText().strip()
            self.change(text=body or None,enabled=bool(body))

    def import_file(self):
        path,_ = QFileDialog.getOpenFileName(self,"导入有权使用的本地文案","","文案包 (*.json)")
        if not path:
            return
        try:
            count = self.lib.import_bundle(read_json(Path(path)))
            self.w.reading_refresh(force=True)
            self.rebuild()
            self.message.setText(f"已导入 {count} 条文案。")
            self.message.show()
        except (ValueError,OSError,RecursionError) as exc:
            QMessageBox.warning(self,"导入未完成",str(exc))

    def export_file(self):
        path,_ = QFileDialog.getSaveFileName(self,"保存含本地摘录的文案库","文案库.nfquotes.json","文案包 (*.json)")
        if path:
            try:
                self.lib.export(Path(path))
            except (ValueError,OSError) as exc:
                QMessageBox.warning(self,"导出未完成",str(exc))
