"""Offline generation of a palette-indexed emitting disc and its optically thin corona."""
from math import atan2, cos, exp, floor, hypot, sin, sqrt, asin
from random import Random
from PySide6.QtGui import QImage, qRgb
from make_sky_textures import DEST, field, cloud


def convection(x,y,sites):
    ix,iy=floor(x),floor(y)
    a=b=100.
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            u,v=sites[(iy+dy)%64][(ix+dx)%64]
            d=(ix+dx+u-x)**2+(iy+dy+v-y)**2
            if d<a: a,b=d,a
            elif d<b: b=d
    return min(1.,3.4*(sqrt(b)-sqrt(a)))


def bake():
    rng=Random(2161)
    sites=[[(rng.uniform(.08,.92),rng.uniform(.08,.92)) for _ in range(64)] for _ in range(64)]
    n=640
    img=QImage(n,n,QImage.Format_Indexed8)
    img.setColorTable([qRgb(i,i,i) for i in range(256)])
    for j in range(n):
        for i in range(n):
            x=(i+.5-n/2)/(n*.345)
            y=(j+.5-n/2)/(n*.345)
            r=hypot(x,y)
            phi=atan2(y,x)
            if r<1:
                z=sqrt(max(0,1-r*r))
                u=atan2(x,z)
                v=asin(y)
                warp=cloud(2.9*u+8,2.9*v)
                fine=cloud(u*10+.9*warp,v*10+warp)
                grain=convection(32*u+2.6*warp,32*v+fine*2,sites)
                lanes=sin(22*v+6*warp+9*fine+2*sin(u*7))
                filaments=exp(-11*lanes*lanes)
                intensity=(.56+.23*warp+.24*fine+.23*(grain-.5)+.15*filaments)*(.79+.21*z**.45)
                idx=64+round(191*max(0,min(1,intensity)))
            else:
                d=r-1
                rays=cloud(11*cos(phi)+d*3,11*sin(phi)+d*4)
                flares=.5+.5*sin(phi*17+7*rays+d*6)
                strength=exp(-d*(17-9*rays))*(.57+.4*flares**5)+.23*exp(-d*71)
                idx=max(0,min(63,round(strength*63)))
            img.setPixel(i,j,idx)
    assert img.save(str(DEST/"photosphere.png"))

if __name__=="__main__": bake()
