"""Bake original diffuse dust fields. Run only when changing the art, never at app startup."""
from pathlib import Path
from math import sin,cos,atan2,hypot,exp,floor
import random
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import Qt

DEST=Path(__file__).resolve().parents[1]/"neurofocus"/"sky_assets"
rng=random.Random(4019)
noise=[[rng.uniform(-1,1) for x in range(128)] for y in range(128)]

def field(x,y):
    ix,iy=floor(x),floor(y)
    fx,fy=x-ix,y-iy
    fx=fx*fx*(3-2*fx)
    fy=fy*fy*(3-2*fy)
    a,b=noise[iy%128],noise[(iy+1)%128]
    return (a[ix%128]*(1-fx)+a[(ix+1)%128]*fx)*(1-fy)+(b[ix%128]*(1-fx)+b[(ix+1)%128]*fx)*fy

def cloud(x,y):
    return sum(amp*field(x*freq+5,y*freq+37) for amp,freq in ((.53,1),(.26,2.1),(.14,4.3),(.08,9),(.04,18),(.02,37)))

def byte(v): return min(255,max(0,round(v)))

def background():
    w,h=1024,630
    img=QImage(w,h,QImage.Format_RGB32)
    for y in range(h):
        for x in range(w):
            u,v=x/w,y/h
            n=cloud(5*u,4*v)
            lane=v-.84+.68*u+.12*sin(u*7)+.12*n
            rim=exp(-((lane+.1*n)/.22)**2)
            filaments=(.42+.7*n+.19*field(21*u,16*v))**2
            density=rim*filaments*2.1
            cut=.48+.52*min(1,abs(lane+.06*sin(u*15)+n*.09)*17)
            warm=exp(-((u-.68)/.29)**2)
            vals=[5+cut*density*(44+44*warm),10+cut*density*(59-5*warm),21+cut*density*(91-12*warm)]
            grain=rng.uniform(-1.6,1.6)
            img.setPixelColor(x,y,QColor(*(byte(i+grain) for i in vals)))
    img.save(str(DEST/"deep-field.jpg"),quality=93)

def galaxy():
    n=470
    img=QImage(n,n,QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    for j in range(n):
        for i in range(n):
            x,y=(i-n/2)/(n*.48),(j-n/2)/(n*.48)
            r=hypot(x,y)
            if r>=1: continue
            theta=atan2(y,x)
            f=cloud(5*x+15,5*y+7)
            angle=2*theta-9*r+.7*sin(3*theta)*r+1.05*f
            arm=(.5+.5*cos(angle))**3
            mask=(1-r**2)**2
            core=exp(-12*r)
            dust=mask*exp(-1.8*r)*(.12+arm*1.8)*(.64+.65*f)**2
            alpha=min(.96,(dust+1.25*core))
            warm=min(1,2*exp(-5*r))
            grain=rng.uniform(-12,12)
            rgb=(149+99*warm+grain,177+45*warm+grain,224-39*warm+grain)
            img.setPixelColor(i,j,QColor(*(byte(v) for v in rgb),byte(255*alpha)))
    img.save(str(DEST/"spiral.png"))

if __name__=="__main__":
    DEST.mkdir(exist_ok=True)
    background()
    galaxy()
