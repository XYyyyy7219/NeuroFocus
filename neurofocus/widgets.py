from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


def label(text, role=""):
    w = QLabel(text)
    w.setProperty("role", role)
    return w


def button(text, role="", handler=None):
    w = QPushButton(text)
    w.setProperty("role", role)
    w.setCursor(Qt.PointingHandCursor)
    if handler:
        w.clicked.connect(handler)
    return w


def box(parent=None, horizontal=False, margins=0, spacing=8):
    layout = (QHBoxLayout if horizontal else QVBoxLayout)(parent)
    layout.setContentsMargins(*((margins,)*4 if isinstance(margins,int) else margins))
    layout.setSpacing(spacing)
    return layout


def card():
    w = QFrame()
    w.setObjectName("card")
    return w


def stylesheet(c):
    return f"""
    QWidget {{color:{c['ink']};font-family:'Segoe UI','Microsoft YaHei UI';font-size:14px;}}
    QMainWindow, QDialog, QWidget#shell, QStackedWidget, QScrollArea, QWidget#form {{background:{c['bg']};}}
    QLabel, QCheckBox {{background:transparent;}}
    QFrame#side {{background:{c['side']};}}
    QLabel[role="brand"] {{color:#F0F5E9;font-size:23px;font-weight:650;}}
    QLabel[role="sidecap"] {{color:#A5BDAA;font-size:12px;}}
    QLabel[role="sidevalue"] {{color:#E2ECDD;font-size:13px;}}
    QPushButton {{background:{c['card']};border:1px solid {c['line']};border-radius:8px;padding:7px 13px;}}
    QPushButton:hover {{background:{c['tint']};}}
    QPushButton:focus, QSpinBox:focus, QComboBox:focus {{border:1px solid {c['accent']};}}
    QPushButton:disabled {{color:{c['muted']};}}
    QPushButton[role="nav"] {{text-align:left;border:0;color:#CBDBCE;background:transparent;padding:12px 14px;}}
    QPushButton[role="nav"]:checked {{background:#315447;color:#F2F7E9;font-weight:600;}}
    QPushButton[role="nav"]:hover {{background:#28493F;}}
    QPushButton[role="primary"] {{background:{c['accent']};color:{c['card']};border:0;font-weight:650;
      border-radius:10px;padding:11px 24px;}}
    QPushButton[role="primary"]:hover {{background:{c['ink']};}}
    QPushButton[role="tool"] {{padding:7px;min-width:18px;}}
    QPushButton:checked {{background:{c['tint']};border-color:{c['accent']};}}
    QFrame#card {{background:{c['card']};border:1px solid {c['line']};border-radius:16px;}}
    QLabel[role="title"] {{font-size:28px;font-weight:650;}}
    QLabel[role="head"] {{font-size:16px;font-weight:650;}}
    QLabel[role="metric"] {{font-size:24px;font-weight:650;}}
    QLabel[role="muted"] {{color:{c['muted']};font-size:13px;}}
    QLabel[role="cap"] {{color:{c['accent']};font-size:12px;font-weight:650;}}
    QLabel[role="pill"] {{color:{c['accent']};background:{c['tint']};padding:4px 11px;border-radius:10px;font-size:12px;}}
    QSpinBox, QComboBox {{background:{c['card']};color:{c['ink']};border:1px solid {c['line']};border-radius:6px;padding:5px 8px;}}
    QComboBox QAbstractItemView, QMenu {{background:{c['card']};color:{c['ink']};selection-background-color:{c['tint']};selection-color:{c['ink']};}}
    QMenu::item {{padding:6px 17px;}}
    QCheckBox {{spacing:8px;}}
    QSlider::groove:horizontal {{height:4px;background:{c['track']};border-radius:2px;}}
    QSlider::handle:horizontal {{background:{c['accent']};width:15px;margin:-6px 0;border-radius:7px;}}
    QTableWidget {{background:{c['card']};color:{c['ink']};border:0;gridline-color:{c['line']};}}
    QHeaderView::section {{background:{c['tint']};color:{c['ink']};border:0;padding:6px;}}
    QScrollArea {{border:0;}}
    QTabWidget::pane {{border:0;background:{c['bg']};}}
    QTabBar::tab {{background:{c['bg']};color:{c['muted']};border:0;border-bottom:2px solid {c['line']};padding:7px 16px;}}
    QTabBar::tab:selected {{color:{c['accent']};border-bottom-color:{c['accent']};font-weight:600;}}
    QToolTip {{background:{c['card']};color:{c['ink']};border:1px solid {c['line']};}}
    """
