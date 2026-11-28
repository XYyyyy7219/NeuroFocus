"""Semantic levels share a camera; each scene item represents real archive data."""
from collections import defaultdict
from math import log1p
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor,QPen,QPainter,QImage,QPixmap,QPainterPath,QTransform,QFontMetricsF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QGraphicsScene
from .stellar import CHILD_SCALE,cluster_position,draw_star,galaxy_position,label_rect,level,member_position
from .distribution import short_time
from .starlight import background, sky_font


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
        self.anchor=QPointF()
        self.count=0
        self.tilt=-23
        self.squash=.50
        self.extent=18.
        self.observing=False
        self.seed=key[0] if group else key[2][0]
        self.setCacheMode(QGraphicsItem.NoCache)

    def boundingRect(self):
        e=self.extent if self.group else max(35.,self.radius*4.1)
        return QRectF(-e,-e,2*e,2*e)

    def shape(self):
        path=QPainterPath()
        if self.group:
            for pt,r in self.points:
                path.addEllipse(pt,max(7.,r),max(7.,r))
            if self.count>10: path.addEllipse(QPointF(),self.extent*.77,self.extent*.52)
        else:
            path.addEllipse(QPointF(),max(9.,self.radius),max(9.,self.radius))
        return path

    def paint(self,p,option,widget):
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        scale=option.levelOfDetailFromTransform(p.worldTransform())
        color=self.color
        if color.lightness()<142: color=color.lighter(min(250,round(14800/max(42,color.lightness()))))
        if self.group:
            if self.count>=11:
                # Diffuse envelope only. All luminous samples below have record IDs.
                from .starlight import texture
                pix=texture("spiral.png")
                e=self.extent*.94
                p.save()
                p.rotate(self.tilt)
                p.setOpacity(min(.54,.15+.06*log1p(self.count)))
                p.drawPixmap(QRectF(-e,-e*self.squash,2*e,2*e*self.squash),pix,QRectF(pix.rect()))
                p.restore()
            for pos,r in self.points:
                p.save()
                p.translate(pos)
                draw_star(p,r,color,level(scale*r),self.seed)
                p.restore()
            return
        if widget is not None:
            view=widget.parentWidget()
            if getattr(view,"observing",None) and not self.observing: p.setOpacity(.24)
        draw_star(p,self.radius,color,level(scale*self.radius,self.observing),self.seed)
        if self.ring and scale*self.radius>=4 and not self.observing:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(tint(color,196),1.15/max(.1,scale)))
            r=self.radius+3.5/scale
            p.drawArc(QRectF(-r,-r,2*r,2*r),29*16,83*16)


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
        self.observing=None
        self._poses={}
        self.labels=[]
        self.show_labels=True
        self.obstacles=lambda:[]
        self.setAlignment(Qt.AlignCenter)
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

    def drawForeground(self,p,rect):
        self.labels=[]
        if not self.show_labels or not self.nodes: return
        viewport=self.viewport().rect()
        visible=QRectF(viewport).adjusted(7,7,-7,-7)
        mapping=self.viewportTransform()
        inverse,ok=mapping.inverted()
        if not ok: return
        # Retain the output-to-viewport transform (including a 2x image export).
        p.save()
        p.setWorldTransform(inverse*p.worldTransform())
        font=sky_font(12)
        p.setFont(font)
        fm=QFontMetricsF(font)
        blocked=list(self.obstacles())
        region=viewport
        if len(self.scope)==2 and len(self.nodes)>=40:
            # At this density only the hovered leaf is annotated. Query nearby items
            # for obstruction tests instead of projecting the entire visible cluster.
            if self.observing or not self.viewport().underMouse():
                p.restore()
                return
            mouse=self.viewport().mapFromGlobal(self.cursor().pos())
            region=viewport.intersected(QRect(mouse.x()-180,mouse.y()-55,360,110))
        items=[item for item in self.items(region,Qt.IntersectsItemBoundingRect) if isinstance(item,Body)]
        candidates=[]
        for item in items:
            anchor=mapping.map(item.mapToScene(item.anchor))
            hover=item.isUnderMouse()
            if item.observing: continue
            if visible.contains(anchor):
                core=max(3,item.radius*mapping.m11()) if not item.group else 4
                blocked.append(QRectF(anchor.x()-core,anchor.y()-core,2*core,2*core))
                if item.active or hover or item.group or (not self.observing and core>=4 and len(self.nodes)<12):
                    candidates.append((item.active,hover,item.count,item,anchor))
        for active,hover,count,item,anchor in sorted(candidates,key=lambda c:c[:3],reverse=True):
            title=item.title
            if item.group and (hover or len(items)<=6): title+=f"  ·  {count}"
            text=fm.elidedText(title,Qt.ElideRight,146)
            w=fm.horizontalAdvance(text)+10
            offset=18 if item.group else max(14,item.radius*mapping.m11()+6)
            place=label_rect(anchor,(w,20),visible,blocked,offset)
            if place is None: continue
            blocked.append(place.adjusted(-3,-2,3,2))
            self.labels.append((item.key,place,anchor))
            end=QPointF(place.left() if place.center().x()>anchor.x() else place.right(),place.center().y())
            p.setPen(QPen(QColor("#9aa9b7"),.7))
            direction=end-anchor
            length=max(1.,(direction.x()**2+direction.y()**2)**.5)
            start=anchor+direction*(min(length-1,4 if item.group else max(3,item.radius*mapping.m11()))/length)
            p.drawLine(start,end)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(9,17,29,172))
            p.drawRoundedRect(place,4,4)
            p.setPen(QColor("#ffe9bc" if active or hover else "#dfe7ee"))
            p.drawText(place,Qt.AlignCenter,text)
            if len(self.labels)>=30: break
        p.restore()

    def hideEvent(self,event):
        self._camera.stop()
        super().hideEvent(event)

    def current_pose(self):
        return self.mapToScene(self.viewport().rect().center()),self.transform().m11()

    def origin(self,path):
        if not path: return QPointF()
        if len(path)==1: return galaxy_position(self.slots[path])
        return cluster_position(self.slots[path],path[0])

    def ascend(self):
        self.enter(self.scope if self.observing else self.scope[:-1],restore=True)

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
        scale=min(1.65,max(.035,min((w-60)/max(1,bounds.width()),max(120,h-190)/max(1,bounds.height()))))
        self.focus_camera(bounds.center(),scale,animate)

    def resizeEvent(self,e):
        super().resizeEvent(e)
        if hasattr(self,"nodes") and self.nodes:
            if self.observing: self.observe_camera(False)
            elif not self.scope: self.frame_scene()

    def populate(self,rows,tags,slots,recenter=False):
        self.rows,self.tags,self.slots=rows,tags,slots
        if self.observing and not any(a.key==self.observing and (a.tag,a.note[0].strip())==self.scope for a in rows):
            self.observing=None
            recenter=True
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
                coords=[]
                for v in point_rows:
                    topic=(v.tag,v.note[0].strip())
                    slot=self.slots[topic]
                    local=member_position(self.slots[topic+(v.key,)],v.tag,slot)*CHILD_SCALE
                    if level==1: local=(cluster_position(slot,v.tag)+local)*CHILD_SCALE
                    radius=(1.4+min(2.6,log1p(v.ms/60000)*.65)) if self.weighted else 3.4
                    if len(items)==1: radius=6.8
                    coords.append((local,radius))
                node.prepareGeometryChange()
                node.points=coords
                node.anchor=sum((pt for pt,_ in coords),QPointF())/len(coords)
                node.count=len(items)
                node.extent=max(18,max(max(abs(pt.x()),abs(pt.y()))+r*4 for pt,r in coords))
                node.tilt=(-28,16,-10,34)[tag.id%4]
                node.squash=(.50,.68,.44,.62)[tag.id%4]
            node.active=level==3 and a.key==self.selected
            node.observing=level==3 and a.key==self.observing
            node.update()
            if level<=2: node.setPos(self.origin(path))
            else: node.setPos(member_position(self.slots[path],a.tag,self.slots[path[:2]]))
            if level==3 and not self.observing and path[1] and prev is not None and self.selected in (prev[2],path[2]):
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

    def enter(self,path,restore=False):
        path=tuple(path)
        self._camera.stop()
        old=self.scope
        point,zoom=self.current_pose()
        if not self.observing:
            self._poses[old]=(point,zoom)
        new=path[:2]
        # Change local charts through the common ancestor, conserving projected space.
        common=0
        for x,y in zip(old,new):
            if x!=y: break
            common+=1
        for i in range(len(old),common,-1):
            prefix=old[:i]
            if prefix not in self.slots: break
            point=self.origin(prefix)+point*CHILD_SCALE
            zoom/=CHILD_SCALE
        for i in range(common+1,len(new)+1):
            point=(point-self.origin(new[:i]))/CHILD_SCALE
            zoom*=CHILD_SCALE
        self.scope=new
        self.observing=path[2] if len(path)==3 else None
        self.selected=self.observing
        self.rebuild(False)
        self.focus_camera(point,max(.006,min(36,zoom)),False)
        if self.observing is not None and path in self.nodes:
            if new not in self._poses:
                self.frame_scene()
                self._poses[new]=self.current_pose()
            self.observe_camera(True)
            self.picked.emit(path[2])
        elif restore and new in self._poses:
            self.focus_camera(*self._poses[new],True)
        else: self.frame_scene(True)

    def observe_camera(self,animate):
        path=self.scope+(self.observing,)
        node=self.nodes.get(path)
        if not node: return
        w,h=self.viewport().width(),self.viewport().height()
        r=max(65,min(h*.218,(w-min(350,w*.36))*.30))
        scale=r/node.radius
        center=node.pos()+QPointF(w*.18/scale,0)
        self.focus_camera(center,scale,animate)

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
            self.enter(hit.key)

    def wheelEvent(self,e):
        self._camera.stop()
        anchor=self.mapToScene(e.position().toPoint())
        factor=1.2 if e.angleDelta().y()>0 else 1/1.2
        zoom=self.transform().m11()*factor
        hit=self.itemAt(e.position().toPoint())
        if zoom>1.85 and isinstance(hit,Body) and len(hit.key)<3:
            self.enter(hit.key)
        elif zoom<.6 and self.scope: self.ascend()
        elif .025<=zoom<=32:
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
