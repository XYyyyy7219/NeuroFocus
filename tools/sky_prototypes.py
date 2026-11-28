"""Interactive design studies. 1/2/3 change layouts; wheel zooms; drag pans; click picks a record."""
import argparse
import math
from datetime import date,timedelta
from pathlib import Path
from statistics import median
from time import perf_counter
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPainter,QPen,QColor
from neurofocus.starlight import background,star,draw_group,sky_font,arm_point
from neurofocus.history import Activity

NAMES=("理论力学","数学","英语","Python")
COLORS=("#f4bd83","#9ed7ee","#c7ace3","#8ad6bc")
CENTERS=((-178,-75),(170,68),(-138,127),(185,-122))
IDS=("astronomy","branches","chronograph")

def fixture(n):
    rows=[]
    for i in range(n):
        tag=i%4
        day=str(date(2025,1,1)+timedelta(days=i//2))
        a=Activity((i+1,day,0,tag),None,None,(7+i%36)*60000)
        if i%3: a.note=("专题 "+str(i%3),"模拟日志","","","")
        rows.append(a)
    return rows

class Prototype(QWidget):
    def __init__(self,rows):
        super().__init__()
        self.rows=rows
        self.mode=0
        self.zoom=1.
        self.offset=QPointF()
        self.down=None
        self.selected=None
        self.hits=[]
        self.resize(920,560)
        self.setWindowTitle("学习宇宙 · 原型比较")
    def paintEvent(self,_):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.mode==0: background(p,QRectF(self.rect()),self.offset)
        else: p.fillRect(self.rect(),QColor(("#10151d","#142524","#191722")[self.mode]))
        self.hits=[]
        p.translate(QPointF(self.rect().center())+self.offset)
        p.scale(self.zoom,self.zoom)
        for tag,center in enumerate(CENTERS):
            rows=[a for a in self.rows if a.tag==tag]
            if not rows: continue
            p.save()
            cx,cy=center
            p.translate(cx,cy)
            color=COLORS[tag]
            if self.mode==0:
                pts=[(arm_point(j,tag),5+a.ms/500000) for j,a in enumerate(rows)]
                draw_group(p,pts,color,140,-20,0.49)
                for (pt,_),a in zip(pts,rows):
                    from PySide6.QtGui import QTransform
                    q=QTransform().rotate(-20).map(QPointF(pt.x()*134.4,pt.y()*65.856))
                    self.hits.append((p.transform().map(q),a))
            else:
                for j,a in enumerate(rows):
                    angle=j*2.39996
                    if self.mode==1:
                        branch=j%3
                        angle=branch*2.094+(j//3%4-1.5)*.19
                        distance=44+(j//3)*7
                        parent=QPointF(30*math.cos(branch*2.094),30*math.sin(branch*2.094))
                        pos=QPointF(distance*math.cos(angle),distance*math.sin(angle))
                        p.setPen(QPen(QColor("#688c86"),.8))
                        p.drawLine(QPointF(),parent)
                        p.drawLine(parent,pos)
                    else:
                        angle=(date.fromisoformat(a.day).timetuple().tm_yday/365)*math.tau
                        r=40+j%3*12
                        pos=QPointF(r*math.cos(angle),r*math.sin(angle))
                        p.setPen(QPen(QColor(color),2.7))
                        p.drawArc(QRectF(-r,-r,2*r,2*r),int(-angle*180/math.pi*16),-60)
                    star(p,pos.x(),pos.y(),9,color)
                    self.hits.append((p.transform().map(pos),a))
            p.setPen(QColor("#e5e9ef"))
            p.setFont(sky_font(14,True))
            p.drawText(QRectF(-110,72,220,22),Qt.AlignCenter,NAMES[tag])
            p.restore()
        p.resetTransform()
        p.setPen(QColor("#e7eef5"))
        p.setFont(sky_font(18,True))
        p.drawText(24,34,("旋臂深空","章节星座","历时轨道")[self.mode])
        p.setFont(sky_font(12))
        p.drawText(24,55,f"{len(self.rows)} 次模拟活动")
        if self.selected: p.drawText(24,self.height()-24,f"{self.selected.day} · {NAMES[self.selected.tag]}")
        p.end()
    def keyPressEvent(self,e):
        if e.text() in ("1","2","3"):
            self.mode=int(e.text())-1
            self.update()
    def wheelEvent(self,e):
        self.zoom=max(.3,min(4,self.zoom*(1.15 if e.angleDelta().y()>0 else 1/1.15)))
        self.update()
    def mousePressEvent(self,e):
        self.down=self.last=e.position()
    def mouseMoveEvent(self,e):
        if self.down is not None:
            self.offset+=e.position()-self.last
            self.last=e.position()
            self.update()
    def mouseReleaseEvent(self,e):
        if self.down is not None and (self.down-e.position()).manhattanLength()<4:
            self.selected=next((a for pos,a in self.hits if (pos-e.position()).manhattanLength()<10),None)
        self.down=None
        self.update()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--capture",type=Path)
    args=parser.parse_args()
    app=QApplication([])
    w=Prototype(fixture(112))
    w.show()
    app.processEvents()
    if not args.capture: sys.exit(app.exec())
    args.capture.mkdir(parents=True,exist_ok=True)
    for mode,name in enumerate(IDS):
        w.mode=mode
        w.update()
        app.processEvents()
        times=[]
        for _ in range(9):
            start=perf_counter()
            shot=w.grab()
            times.append(1000*(perf_counter()-start))
        assert shot.save(str(args.capture/(name+".png")))
        print(name,round(median(times),2),"ms")
