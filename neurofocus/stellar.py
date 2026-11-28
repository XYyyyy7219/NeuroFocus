"""Projection-sensitive star rendering and nested, deterministic chart coordinates."""
from functools import lru_cache
from math import sin,cos,sqrt,log1p
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QBrush,QColor,QImage,QPainter,QPixmap,QRadialGradient,qRgba
from .starlight import ASSETS,star,alpha

# Child charts are expressed in local coordinates. A chart change preserves the
# projected position by composing its origin and this uniform scale with the camera.
CHILD_SCALE=.23


def galaxy_position(slot):
    a=slot*2.39996323+.26
    r=245*sqrt(slot)
    return QPointF(r*1.13*cos(a),r*.83*sin(a))


def cluster_position(slot,tag):
    if slot==0: return QPointF()
    a=slot*2.39996323+tag*.91
    r=285*sqrt(slot)/(1+.21*sqrt(slot))
    return QPointF(r*cos(a),r*.78*sin(a))


def member_position(slot,tag,topic_slot):
    if slot==0: return QPointF()
    # Uniform angular spacing with an ID-specific winding. Append-only slots
    # preserve positions; the soft radius limit keeps the parent inset bounded.
    a=slot*2.39996323+.70*log1p(slot)+tag*.7+topic_slot
    r=78*sqrt(slot)/(1+.019*sqrt(slot))
    return QPointF(r*cos(a),r*(.64+(tag%4)*.065)*sin(a))


def level(pixel_radius,observing=False):
    if observing: return 3
    if pixel_radius>=24: return 2
    return 0 if pixel_radius<4 else 1


@lru_cache(maxsize=1)
def relief():
    image=QImage(str(ASSETS/"photosphere.png"))
    if image.isNull(): raise RuntimeError("无法加载恒星表面资源")
    return image.convertToFormat(QImage.Format_Indexed8) if image.format()!=QImage.Format_Indexed8 else image


@lru_cache(maxsize=12)
def surface(hue):
    c=QColor(hue)
    h,s,_=c.getHsv()[:3]
    hot=QColor.fromHsv(max(0,h),min(215,max(75,s+35)),248) if s>20 else QColor("#c1d2dc")
    def mix(a,b,t): return [round(x+(y-x)*t) for x,y in zip(a,b)]
    base=hot.getRgb()[:3]
    lo=[round(i*.23) for i in base]
    hi=mix(base,(255,249,219),.85)
    table=[qRgba(*base,round(200*(i/63)**1.1)) for i in range(64)]
    for i in range(192):
        t=min(1,max(0,(i/191-.14)/.70))
        rgb=mix(lo,base,t/.64) if t<.64 else mix(base,hi,(t-.64)/.36)
        table.append(qRgba(*rgb,255))
    image=QImage(relief())
    image.setColorTable(table)
    return QPixmap.fromImage(image)


@lru_cache(maxsize=64)
def mid_disc(hue):
    pix=QPixmap(192,192)
    pix.fill(Qt.transparent)
    painter=QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(96,96)
    r=24
    color=QColor(hue)
    star(painter,0,0,r*4,hue)
    gradient=QRadialGradient(0,0,r)
    for pos,tint in ((0,QColor("#fff0ce")),(.66,color.lighter(147)),(.95,color),(1,alpha(color,185))):
        gradient.setColorAt(pos,tint)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawEllipse(QPointF(),r,r)
    painter.end()
    return pix


def draw_star(p,r,color,detail,seed=0):
    hue=color.name()
    if detail==0:
        star(p,0,0,2.8*r,hue)
        return
    if detail==1:
        pix=mid_disc(hue)
        p.drawPixmap(QRectF(-4*r,-4*r,8*r,8*r),pix,QRectF(pix.rect()))
    else:
        star(p,0,0,4*r,hue)
        pix=surface(hue)
        p.save()
        p.rotate((seed*137)%360)
        size=r/.345
        p.drawPixmap(QRectF(-size/2,-size/2,size,size),pix,QRectF(pix.rect()))
        p.restore()


def label_rect(anchor,size,visible,blocked,offset):
    """Four short callout candidates. Omit a label if no local placement fits."""
    w,h=size
    for dx,dy in ((offset,-h-4),(offset,4),(-offset-w,-h-4),(-offset-w,4)):
        rect=QRectF(anchor.x()+dx,anchor.y()+dy,w,h)
        if visible.contains(rect) and not any(rect.intersects(b) for b in blocked):
            return rect
    return None
