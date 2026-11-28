import math
from PySide6.QtCore import Qt, QRectF, QPointF, QByteArray
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QIcon, QPainterPath
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QSizePolicy


LIGHT = dict(bg="#F4F5EF", card="#FEFFFA", ink="#203D35", muted="#586D60", line="#D9E1D6",
             tint="#E7EFE0", accent="#31745B", track="#D9E6D5", side="#132F28", coral="#A4573E")
DARK = dict(bg="#17241F", card="#1C3028", ink="#EBF3E7", muted="#A8BBAA", line="#395044",
            tint="#2B4436", accent="#9ACBA5", track="#354F40", side="#10231E", coral="#E9A78B")

PATHS = {
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v5l3 1M9 2h6"/>',
    "chart": '<path d="M4 19h16M6 15v-4m6 4V5m6 10V9"/>',
    "settings": '<path d="M4 6h9m4 0h3M4 12h3m4 0h9M4 18h10m4 0h2"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
    "mini": '<rect x="3" y="4" width="18" height="16" rx="3"/><rect x="11" y="11" width="7" height="6" rx="1"/>',
    "pin": '<path d="m8 3 9 0-2 5 3 4v2H6v-2l4-4zM12 14v7"/>',
    "play": '<path fill="currentColor" stroke="none" d="M7 4.7a1 1 0 0 1 1.6-.8l12 7.2a1 1 0 0 1 0 1.8l-12 7.2a1 1 0 0 1-1.6-.9z"/>',
    "pause": '<path d="M8 5v14m8-14v14" stroke-width="3.5"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "reset": '<path d="M4 5v5h5M4.6 10a8 8 0 1 1 .5 6"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',
    "moon": '<path d="M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11z"/>',
    "leaf": '<path d="M5 18C1 8 10 4 20 4c0 10-4 17-13 14m-3 3L16 8"/>',
    "cycle": '<path d="M3 10a9 9 0 0 1 15-5l2 2m0-5v6h-6M21 14A9 9 0 0 1 6 19l-2-2m0 5v-6h6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    "download": '<path d="M12 2v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    "volume": '<path d="M3 9h4l5-5v16l-5-5H3zm13-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
    "logo": '<g stroke-width="2.5"><path d="M2 17V9c0-6 7-7 10-2l8 12"/><path d="M4 5l9 14c3 4 9 2 9-3V7"/><path d="m6 19 2-7m8-1 2-7"/></g>',
}


def icon(name, color):
    body = PATHS[name].replace("currentColor", color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    pix = QPixmap(72,72)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    return QIcon(pix)


def font(size, weight=QFont.Normal, family="Microsoft YaHei UI"):
    f = QFont(family)
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def stamp(ms, count_up=False):
    seconds = max(0, ms//1000 if count_up else math.ceil(ms/1000))
    if count_up and seconds>=3600: return f"{seconds//3600}:{seconds//60%60:02}:{seconds%60:02}"
    return f"{seconds//60:02}:{seconds%60:02}"


class Dial(QWidget):
    def __init__(self):
        super().__init__()
        self.colors = LIGHT
        self.state = ("90:00", "准备专注", 0., "focus")
        self.mode = 'neuro'
        self.setMinimumSize(200,200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("阶段倒计时")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width()-6, self.height()-6, 336)
        p.translate(self.width()/2,self.height()/2)
        p.scale(side/300,side/300)
        t, title, ratio, phase = self.state
        c = self.colors
        dark=c==DARK
        accent={"pomo":c['coral'],"deep":"#9FBFD1" if dark else "#496E89",
                "flow":"#C2B6D5" if dark else "#78628A"}.get(self.mode,c['accent'])
        if phase=='micro': accent=c['coral']
        rect = QRectF(-131,-131,262,262)
        p.setPen(QPen(QColor(accent if ratio is None else c["track"]),2 if ratio is None else 6))
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(accent),6,Qt.SolidLine,Qt.RoundCap))
        if ratio is not None:
            p.drawArc(rect,90*16,-round(5760*ratio))
            a = ratio*2*math.pi-math.pi/2
            pt = QPointF(131*math.cos(a),131*math.sin(a))
            p.setBrush(QColor(accent))
            p.setPen(QPen(QColor(c["card"]),2))
            p.drawEllipse(pt,5.5,5.5)
        for i in range(60):
            p.setPen(QPen(QColor(c["muted"] if i%5==0 else c["line"]),1))
            p.drawLine(QPointF(0,-117),QPointF(0,-111 if i%5==0 else -114))
            p.rotate(6)
        p.setPen(QColor(c["muted"]))
        p.setFont(font(13))
        p.drawText(QRectF(-105,-57,210,25),Qt.AlignCenter,title)
        p.setPen(QColor(c["ink"]))
        p.setFont(font(61 if len(t)<6 else 51,QFont.DemiBold,"Segoe UI Variable Display"))
        p.drawText(QRectF(-120,-40,240,80),Qt.AlignCenter,t)
        p.setPen(QColor(c["muted"]))
        p.setFont(font(11,QFont.DemiBold,"Segoe UI"))
        unit="已 学 时 间" if ratio is None else "M I N   /   S E C"
        p.drawText(QRectF(-100,43,200,22),Qt.AlignCenter,unit)
        p.end()


class Terrain(QWidget):
    """Quiet contour lines clipped to the sidebar's lower edge."""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(128)
    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#305548"),1))
        for i in range(11):
            path=QPainterPath(QPointF(-12,86+i*6))
            path.cubicTo(52,108+i*5,69,8+i*4,124,34+i*5)
            path.cubicTo(158,49+i*5,163,73+i*4,210,51+i*4)
            p.drawPath(path)
        p.end()
