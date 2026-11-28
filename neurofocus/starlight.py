"""Optical sprites and static diffuse fields for the learning sky. No idle render loop."""
from functools import lru_cache
from math import cos,sin,pi,sqrt
from pathlib import Path
from random import Random
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QPixmap,QRadialGradient,QPainter,QPen,QBrush,QFont

ASSETS=Path(__file__).with_name("sky_assets")


@lru_cache(maxsize=3)
def texture(name):
    return QPixmap(str(ASSETS/name))


def alpha(color,a):
    c=QColor(color)
    c.setAlpha(a)
    return c


def sky_font(size,bold=False):
    f=QFont("Microsoft YaHei UI")
    f.setPixelSize(size)
    f.setBold(bold)
    return f


@lru_cache(maxsize=128)
def emitter(color):
    # One symmetrical photometric footprint; apparent hue survives the white core.
    pix=QPixmap(128,128)
    pix.fill(Qt.transparent)
    p=QPainter(pix)
    g=QRadialGradient(64,64,64)
    for pos,c in [(0,"#fffef6"),(.056,"#fffffb"),(.105,QColor(color).lighter(160)),
                  (.18,alpha(color,170)),(.37,alpha(color,53)),(.66,alpha(color,16)),(1,alpha(color,0))]:
        g.setColorAt(pos,QColor(c))
    p.fillRect(pix.rect(),QBrush(g))
    p.end()
    return pix


def star(p,x,y,r,color):
    pix=emitter(color)
    p.drawPixmap(QRectF(x-r,y-r,2*r,2*r),pix,QRectF(pix.rect()))


@lru_cache(maxsize=1)
def dust():
    rng=Random(29117)
    return [(rng.random(),rng.random(),rng.uniform(.27,.9),rng.randrange(48,145)) for _ in range(650)]


def background(p,bounds,offset=QPointF(),low=False):
    p.fillRect(bounds,QColor("#070d1a"))
    pix=texture("deep-field.jpg")
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawPixmap(bounds,pix,QRectF(pix.rect()))
    p.setPen(Qt.NoPen)
    for x,y,r,a in dust()[::3 if low else 1]:
        # Subpixel, achromatic, noninteractive background stars.
        px=(x*bounds.width()+offset.x()*r*.055)%max(1,bounds.width())
        py=(y*bounds.height()+offset.y()*r*.055)%max(1,bounds.height())
        p.setBrush(QColor(191,202,222,a))
        p.drawEllipse(QPointF(bounds.left()+px,bounds.top()+py),r,r)


def arm_point(slot,seed=0):
    """Stable, bounded two-arm sample independent of the visible population."""
    rng=Random(seed*3917+slot*10007)
    if slot==0: return QPointF()
    r=(.045+.89*((.29+slot*.61803398875)%1)**.66)
    theta=(slot%2)*pi+4.5*r+rng.uniform(-.54,.54)
    return QPointF(r*cos(theta),r*sin(theta))


def draw_group(p,points,palette,extent,tilt,squash,opacity=.9):
    p.save()
    p.rotate(tilt)
    p.scale(1,squash)
    pix=texture("spiral.png")
    p.setOpacity(opacity)
    p.drawPixmap(QRectF(-extent,-extent,2*extent,2*extent),pix,QRectF(pix.rect()))
    p.setOpacity(1)
    p.restore()
    p.save()
    p.rotate(tilt)
    for pos,r in points:
        star(p,pos.x()*extent*.96,pos.y()*extent*squash*.96,r,palette)
    p.restore()
