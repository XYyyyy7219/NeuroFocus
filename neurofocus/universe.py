"""Semantic levels share a camera; each scene item represents real archive data."""
from collections import defaultdict
from math import cos, sin, sqrt, log1p
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor,QPen,QPainter,QImage,QPixmap,QPainterPath,QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QGraphicsScene
from .distribution import short_time
from .starlight import background, draw_group, arm_point, sky_font, star


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
        self.points=()
        self.count=0
        self.tilt=-23
        self.squash=.50
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache if group else QGraphicsItem.NoCache)

    def boundingRect(self):
        if self.group:
            return QRectF(-150,-100,300,217)
        return QRectF(-85,-40,170,87)

    def shape(self):
        path=QPainterPath()
        if self.group:
            path.addEllipse(QRectF(-132,-66,264,139))
            path.addRect(QRectF(-72,62,144,45))
        else:
            path.addEllipse(QPointF(),max(9,self.radius*.64),max(9,self.radius*.64))
        return path

    def paint(self,p,option,widget):
        from PySide6.QtWidgets import QStyle
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hovered=bool(option.state & QStyle.State_MouseOver)
        color=self.color
        if color.lightness()<146: color=color.lighter(min(260,round(15000/max(40,color.lightness()))))
        tint_name=color.name()
        if self.group:
            draw_group(p,self.points,tint_name,133,self.tilt,self.squash,
                       min(.97,.35+.14*log1p(self.count)))
            p.setFont(sky_font(15,True))
            p.setPen(QColor("#f4f0e9" if hovered else "#d6e1eb"))
            p.drawText(QRectF(-118,65,236,24),Qt.AlignCenter,p.fontMetrics().elidedText(self.title,Qt.ElideRight,226))
            p.setFont(sky_font(10))
            p.setPen(QColor("#b1c2d7"))
            p.drawText(QRectF(-100,91,200,17),Qt.AlignCenter,f"{self.count} 次活动")
            if hovered:
                p.setPen(QPen(color,1))
                p.drawLine(QPointF(-12,62),QPointF(12,62))
            return
        r=self.radius
        star(p,0,0,r*1.9,tint_name)
        p.setBrush(Qt.NoBrush)
        if self.ring:
            p.setPen(QPen(tint(color,205),1.1))
            p.drawArc(QRectF(-9,-9,18,18),25*16,94*16)
        if self.active or hovered:
            p.setPen(QPen(QColor("#f0e2c8"),1))
            rect=QRectF(-16,-16,32,32)
            for i in range(4): p.drawArc(rect,(i*90+26)*16,38*16)
            p.setFont(sky_font(12))
            p.drawText(QRectF(-80,21,160,21),Qt.AlignCenter,self.title)


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
        self.low=False
        self._back=None
        self._fit_pending=True
        self._camera=QVariantAnimation(self)
        self._camera.setDuration(240)
        self._camera.setEasingCurve(QEasingCurve.OutCubic)
        self._camera.setStartValue(0.)
        self._camera.setEndValue(1.)
        self._camera.valueChanged.connect(self.camera_frame)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setMouseTracking(True)

    def drawBackground(self,p,rect):
        viewport=self.viewport()
        width,height=viewport.width(),viewport.height()
        if min(width,height)<1: return
        key=(width,height,self.low,viewport.devicePixelRatioF())
        margin=18
        if self._back is None or self._back[0]!=key:
            ratio=min(1.5,key[-1])
            pix=QPixmap(round((width+2*margin)*ratio),round((height+2*margin)*ratio))
            pix.setDevicePixelRatio(ratio)
            painter=QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            background(painter,QRectF(0,0,width+2*margin,height+2*margin),low=self.low)
            painter.end()
            self._back=(key,pix)
        area=self.mapToScene(viewport.rect()).boundingRect()
        from math import tanh
        delta=QPointF() if self.low else area.center()
        dx=margin*(1+tanh(delta.x()/1200))
        dy=margin*(1+tanh(delta.y()/1200))
        pix=self._back[1]
        ratio=pix.devicePixelRatio()
        p.drawPixmap(area,pix,QRectF(dx*ratio,dy*ratio,width*ratio,height*ratio))

    def set_low(self,value):
        self.low=value
        if value: self._camera.stop()
        self._back=None
        self.viewport().update()

    def camera_frame(self,f):
        pos=self._from+(self._to-self._from)*f
        scale=self._scale0*(self._scale1/self._scale0)**f
        self.setTransform(QTransform.fromScale(scale,scale))
        self.centerOn(pos)

    def focus_camera(self,point,scale,animate):
        self._camera.stop()
        self._from=self.mapToScene(self.viewport().rect().center())
        self._to=point
        self._scale0=self.transform().m11()
        self._scale1=scale
        if animate and self.isVisible() and not self.low: self._camera.start()
        else: self.camera_frame(1.)

    def frame_scene(self,animate=False):
        if not self.nodes:
            self.focus_camera(QPointF(),1,False)
            return
        bounds=self.scene().itemsBoundingRect()
        w,h=self.viewport().width(),self.viewport().height()
        scale=min(1.65,max(.035,min((w-35)/max(1,bounds.width()),(h-100)/max(1,bounds.height()))))
        self.focus_camera(bounds.center(),scale,animate)

    def resizeEvent(self,e):
        super().resizeEvent(e)
        if hasattr(self,"nodes") and self.nodes and not self.scope: self.frame_scene()

    def populate(self,rows,tags,slots,recenter=False):
        self.rows,self.tags,self.slots=rows,tags,slots
        self.rebuild(recenter or self._fit_pending)
        self._fit_pending=not bool(rows)

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
            if level<3:
                # At the overview, sample bounded detail but always show the true count.
                # The stable slot within the full tag survives filters and timeline playback.
                if len(items)<=160:
                    point_rows=items
                else:
                    # Vary the offset inside each bin to avoid aliasing a spiral arm.
                    point_rows=[items[int((j+(.31+j*.61803398875)%1)*len(items)/160)]
                                for j in range(160)]
                coords=tuple((arm_point(self.slots[("tag-member",v.key)],tag.id),
                              (5.5+min(6,log1p(v.ms/60000)*1.4)) if self.weighted else 8) for v in point_rows)
                node.points=coords
                node.count=len(items)
                node.tilt=(-28,15,-9,32)[self.slots[path]%4]
                node.squash=(.52,.66,.43,.56)[self.slots[path]%4]
            node.active=level==3 and a.key==self.selected
            node.update()
            node.setPos(orbit(self.slots[path])*(2.8 if level<3 else .84))
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
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-2100,-1600,2100,1600))
        if recenter: self.frame_scene()
        else: self.centerOn(center)
        self.changed.emit()

    def enter(self,path):
        self._camera.stop()
        self.scope=path[:2]
        if len(path)==3: self.selected=path[2]
        self.rebuild(False)
        if len(path)<3: self.frame_scene(True)
        if len(path)==3 and path in self.nodes:
            self.focus_camera(self.nodes[path].pos(),1.25,True)
            self.picked.emit(path[2])

    def mousePressEvent(self,e):
        self._camera.stop()
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
        self._camera.stop()
        anchor=self.mapToScene(e.position().toPoint())
        factor=1.2 if e.angleDelta().y()>0 else 1/1.2
        zoom=self.transform().m11()*factor
        hit=self.itemAt(e.position().toPoint())
        if zoom>1.85 and isinstance(hit,Body) and len(hit.key)<3:
            self.enter(hit.key)
        elif zoom<.6 and self.scope: self.enter(self.scope[:-1])
        elif .035<=zoom<=5:
            center=self.mapToScene(self.viewport().rect().center())
            self.focus_camera(anchor+(center-anchor)/factor,zoom,True)
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
    per_tag=defaultdict(int)
    for a in rows:
        slots[("tag-member",a.key)]=per_tag[a.tag]
        per_tag[a.tag]+=1
        path=(a.tag,a.note[0].strip(),a.key)
        for i in range(1,4):
            key=path[:i]
            if key not in slots:
                slots[key]=counts[key[:-1]]
                counts[key[:-1]]+=1
    return slots
