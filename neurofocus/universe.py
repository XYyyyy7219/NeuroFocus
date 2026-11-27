"""Semantic levels share a camera; each scene item represents real archive data."""
from collections import defaultdict
from math import cos, sin, sqrt, log1p
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QBrush, QPen, QPainter, QRadialGradient, QImage, QFont
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QGraphicsScene
from .distribution import short_time


def orbit(slot):
    angle = slot*2.399963229728653
    radius = 90*sqrt(slot)
    return QPointF(radius*cos(angle)*1.25,radius*sin(angle)*0.78)


def tint(color, alpha):
    c=QColor(color)
    c.setAlpha(alpha)
    return c


class Body(QGraphicsItem):
    def __init__(self,key,title,tip,color,radius,ring,group):
        super().__init__()
        self.key,self.title,self.color=key,title,QColor(color)
        self.radius,self.ring,self.group=radius,ring,group
        self.active=False
        self.setToolTip(tip)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self):
        extent=max(84,self.radius*2.4)
        return QRectF(-extent,-extent,2*extent,2*extent)

    def shape(self):
        from PySide6.QtGui import QPainterPath
        p=QPainterPath()
        p.addEllipse(QPointF(),self.radius+5,self.radius+5)
        return p

    def paint(self,p,option,widget):
        from PySide6.QtWidgets import QStyle
        r=self.radius
        hovered=bool(option.state & QStyle.State_MouseOver)
        halo=QRadialGradient(0,0,r*2.4)
        halo.setColorAt(0,tint(self.color,140))
        halo.setColorAt(.48,tint(self.color,60 if hovered else 31))
        halo.setColorAt(1,tint(self.color,0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(),r*2.4,r*2.4)
        sphere=QRadialGradient(-r*.28,-r*.36,r*1.55)
        sphere.setColorAt(0,self.color.lighter(215))
        sphere.setColorAt(.36,self.color.lighter(135))
        sphere.setColorAt(.72,self.color)
        sphere.setColorAt(1,self.color.darker(235))
        p.setBrush(QBrush(sphere))
        p.drawEllipse(QPointF(),r,r)
        p.setBrush(Qt.NoBrush)
        if self.ring:
            p.save()
            p.rotate(-21)
            p.setPen(QPen(tint(self.color.lighter(175),200),1.5))
            p.drawEllipse(QPointF(),r*1.52,r*.56)
            p.restore()
        if self.active or hovered:
            p.setPen(QPen(QColor("#e7efec"),1.5))
            p.drawEllipse(QPointF(),r+5,r+5)
        if self.group or self.active or hovered:
            p.setPen(QColor("#e0e8f2"))
            f=QFont("Microsoft YaHei UI")
            f.setPixelSize(13)
            p.setFont(f)
            p.drawText(QRectF(-80,r+8,160,20),Qt.AlignCenter,p.fontMetrics().elidedText(self.title,Qt.ElideRight,138))


class Sky(QGraphicsView):
    picked=Signal(object)
    changed=Signal()
    def __init__(self):
        super().__init__()
        scene=QGraphicsScene(self)
        self.setScene(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumHeight(220)
        self.setAccessibleName("学习星图")
        self.scope=()
        self.nodes={}
        self.edges={}
        self.empty=None
        self.selected=None
        self.weighted=True
        self._press=None
        self.rows=[]
        self.tags={}
        self.slots={}

    def drawBackground(self,p,rect):
        p.save()
        # Paint in camera coordinates. Background dust stays separate from the data layer.
        p.resetTransform()
        bounds=p.viewport()
        p.fillRect(bounds,QColor("#0b1424"))
        mist=QRadialGradient(bounds.width()*.38,bounds.height()*.64,bounds.width()*.67)
        mist.setColorAt(0,QColor("#203347"))
        mist.setColorAt(.56,QColor("#142334"))
        mist.setColorAt(1,QColor("#0b1424"))
        p.fillRect(bounds,QBrush(mist))
        p.setPen(Qt.NoPen)
        for i in range(120):
            x=((i*2654435761)%997)/997*bounds.width()
            y=((i*1597334677)%991)/991*bounds.height()
            p.setBrush(QColor(186,212,228,35+i%50))
            p.drawEllipse(QPointF(x,y),.7,.7)
        p.restore()

    def populate(self,rows,tags,slots,recenter=False):
        self.rows,self.tags,self.slots=rows,tags,slots
        self.rebuild(recenter)

    def rebuild(self,recenter=True):
        center=self.mapToScene(self.viewport().rect().center())
        groups=defaultdict(list)
        for a in self.rows:
            path=(a.tag,a.note[0].strip(),a.key)
            if path[:len(self.scope)]==self.scope:
                groups[path[:len(self.scope)+1]].append(a)
        if self.empty is not None:
            self.scene().removeItem(self.empty)
            self.empty=None
        for path in self.nodes.keys()-groups.keys():
            self.scene().removeItem(self.nodes.pop(path))
        prev=None
        edges=set()
        for path,items in groups.items():
            a=items[0]
            tag=self.tags[a.tag]
            level=len(path)
            title=tag.name if level==1 else (path[1] or "未填写主题") if level==2 else a.day
            ms=sum(v.ms for v in items)
            r=26 if level==1 else 19 if level==2 else 8
            if self.weighted: r+=min(8,log1p(ms/60000)*1.7)
            tip=f"{title}　·　{short_time(ms)}　·　{len(items)} 次活动"
            ring=level==3 and any(a.note)
            node=self.nodes.get(path)
            if node is None:
                node=Body(path,title,tip,tag.color,r,ring,level<3)
                self.scene().addItem(node)
                self.nodes[path]=node
            elif node.toolTip()!=tip or node.color.name()!=tag.color.lower() or node.ring!=ring or node.radius!=r:
                node.prepareGeometryChange()
                node.radius,node.color,node.title,node.ring=r,QColor(tag.color),title,ring
                node.setToolTip(tip)
                node.update()
            node.active=level==3 and a.key==self.selected
            node.update()
            node.setPos(orbit(self.slots[path]))
            if level==3 and path[1] and prev is not None and self.selected in (prev[2],path[2]):
                edge=(prev,path)
                edges.add(edge)
                other=self.nodes[prev]
                if edge not in self.edges:
                    self.edges[edge]=self.scene().addLine(0,0,0,0)
                    self.edges[edge].setZValue(-1)
                self.edges[edge].setLine(other.x(),other.y(),node.x(),node.y())
                self.edges[edge].setPen(QPen(tint(tag.color,65),1))
            prev=path
        for edge in self.edges.keys()-edges:
            self.scene().removeItem(self.edges.pop(edge))
        if not groups:
            message=self.scene().addSimpleText("当前范围没有学习活动")
            message.setBrush(QColor("#ced9e3"))
            message.setPos(-72,-10)
            self.empty=message
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-360,-260,360,260))
        if recenter:
            self.resetTransform()
            self.centerOn(QPointF())
            if not self.scope and groups:
                bounds=self.scene().itemsBoundingRect()
                if bounds.width()>self.viewport().width() or bounds.height()>self.viewport().height():
                    self.fitInView(bounds,Qt.KeepAspectRatio)
        else: self.centerOn(center)
        self.changed.emit()

    def enter(self,path):
        self.scope=path[:2]
        if len(path)==3: self.selected=path[2]
        self.rebuild()
        if len(path)==3 and path in self.nodes:
            self.centerOn(self.nodes[path])
            self.picked.emit(path[2])

    def mousePressEvent(self,e):
        self._press=e.position()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self,e):
        hit=self.itemAt(e.position().toPoint())
        click=self._press is not None and (e.position()-self._press).manhattanLength()<5
        super().mouseReleaseEvent(e)
        self._press=None
        if click and isinstance(hit,Body) and e.button()==Qt.LeftButton:
            if len(hit.key)<3: self.enter(hit.key)
            else:
                self.selected=hit.key[2]
                self.rebuild(False)
                self.picked.emit(self.selected)

    def wheelEvent(self,e):
        factor=1.2 if e.angleDelta().y()>0 else 1/1.2
        zoom=self.transform().m11()*factor
        hit=self.itemAt(e.position().toPoint())
        if zoom>1.85 and isinstance(hit,Body) and len(hit.key)<3:
            self.enter(hit.key)
        elif zoom<.6 and self.scope: self.enter(self.scope[:-1])
        elif .18<=zoom<=4: self.scale(factor,factor)
        e.accept()

    def export(self,path):
        size=self.viewport().size()*2
        image=QImage(size,QImage.Format_ARGB32)
        image.fill(QColor("#0b1424"))
        p=QPainter(image)
        self.render(p,QRectF(0,0,size.width(),size.height()))
        p.end()
        return image.save(path)


def layout_slots(rows):
    """Allocate before filtering so the date slider never reflows surviving nodes."""
    slots={}
    counts=defaultdict(int)
    for a in rows:
        path=(a.tag,a.note[0].strip(),a.key)
        for i in range(1,4):
            key=path[:i]
            if key not in slots:
                slots[key]=counts[key[:-1]]
                counts[key[:-1]]+=1
    return slots
