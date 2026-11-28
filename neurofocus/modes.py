"""Immutable session policies and the local catalog of editable focus profiles."""
from dataclasses import dataclass, asdict, replace
import json
from uuid import uuid4
from .config import LIMITS

LEGACY_FIELDS = ("focus","long","micro","low","high","micro_on","inclusive","auto_long","auto_next")
RESTS = ("short","long","manual")
REST_LABELS = {"short":"短休息","long":"长休息","manual":"自主休息","micro":"微休息"}
NAMES = {"neuro":"NeuroFocus","pomo":"Pomodoro","deep":"Deep Work","flow":"Flowtime"}
DESCRIPTIONS = {"neuro":"随机微休息","pomo":"番茄工作法","deep":"连续专注","flow":"自由专注"}
ICONS = {"neuro":"leaf","pomo":"cycle","deep":"clock","flow":"timer"}


@dataclass(frozen=True)
class Profile:
    id: str = "neuro"
    name: str = "NeuroFocus"
    count_up: bool = False
    focus: int = 90
    long: int = 20
    short: int = 5
    short_on: bool = False
    grouped: bool = False
    rounds: int = 4
    low: int = 3
    high: int = 5
    micro: int = 10
    micro_on: bool = True
    inclusive: bool = True
    auto_long: bool = True
    auto_next: bool = False
    suggest: bool = False
    break_steps: tuple = (5,8,15,20)
    reminder: int = 0

    def __post_init__(self):
        if not isinstance(self.name,str) or not 1<=len(self.name.strip())<=32:
            raise ValueError("模式名称应为 1–32 个字符")
        if not isinstance(self.id,str) or not self.id:
            raise ValueError("模式 ID 无效")
        for key,(lo,hi) in {**{k:v for k,v in LIMITS.items() if k!="volume"},
                            "short":(1,180),"rounds":(2,24),"reminder":(0,720)}.items():
            v=getattr(self,key)
            if type(v) is not int or not lo<=v<=hi: raise ValueError("计时参数超出范围："+key)
        for k in ("count_up","short_on","grouped","micro_on","inclusive","auto_long","auto_next","suggest"):
            if type(getattr(self,k)) is not bool: raise ValueError("开关参数无效："+k)
        if self.low>self.high: raise ValueError("随机间隔下限不能超过上限")
        if len(self.break_steps)!=4 or any(type(v) is not int or not 1<=v<=180 for v in self.break_steps):
            raise ValueError("四档休息建议需在 1–180 分钟内")
        object.__setattr__(self,"break_steps",tuple(self.break_steps))

    def rest(self, index):
        return "short" if self.short_on and (not self.grouped or index<self.rounds) else "long"

    def suggested_minutes(self, actual, index=1):
        if self.suggest:
            return self.break_steps[sum(actual>=cut*60000 for cut in (25,50,90))]
        return self.short if self.rest(index)=="short" else self.long

    def summary(self):
        if self.count_up: return "正向计时 · 自主休息"
        if self.grouped and self.short_on: return f"{self.focus} / {self.short} 分钟 · 每组 {self.rounds} 轮"
        if self.grouped: return f"{self.focus} 分钟 · 每组 {self.rounds} 轮"
        return f"{self.focus} 分钟专注 · {self.long} 分钟休息"


def default(key, name=None):
    if key=="neuro": return Profile()
    common=dict(id=key,name=name or NAMES.get(key,"我的专注"),micro_on=False)
    if key=="pomo": return Profile(**common,focus=25,short_on=True,grouped=True)
    if key=="flow": return Profile(**common,count_up=True,long=5,suggest=True)
    return Profile(**common,focus=60 if key=="deep" else 45,long=15 if key=="deep" else 10)


def from_settings(settings):
    return replace(default("neuro"),**{k:getattr(settings,k) for k in LEGACY_FIELDS})


class Profiles:
    def __init__(self,db,settings):
        self.db=db
        self.items={k:default(k) for k in NAMES}
        self.items.update((k,Profile(**json.loads(v))) for k,v in db.execute("SELECT id, config FROM focus_profiles"))
        self.items["neuro"]=from_settings(settings)
        row=db.execute("SELECT mode FROM focus_selected WHERE slot=1").fetchone()
        self.selected=row[0] if row and row[0] in self.items else "neuro"

    def create(self): return default("custom-"+uuid4().hex)

    def save(self,p):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO focus_profiles VALUES(?,?)",(p.id,json.dumps(asdict(p),ensure_ascii=False)))
        self.items[p.id]=p

    def select(self,key):
        if key not in self.items: raise ValueError("模式不存在")
        with self.db: self.db.execute("INSERT OR REPLACE INTO focus_selected VALUES(1,?)",(key,))
        self.selected=key

    def delete(self,key):
        if key in NAMES: raise ValueError("内置模式不能删除")
        with self.db:
            self.db.execute("DELETE FROM focus_profiles WHERE id=?",(key,))
            self.db.execute("UPDATE focus_selected SET mode='neuro' WHERE mode=?",(key,))
        self.items.pop(key,None)
        if self.selected==key: self.selected="neuro"


def snapshot_title(raw):
    if not raw: return "旧版记录 · 参数未知"
    c=json.loads(raw)
    name=c.get("name","旧版 NeuroFocus")
    timing="正向计时" if c.get("count_up") else f"{c['focus']} 分钟专注"
    group=f" · 第 {c.get('round_index',1)}/{c['rounds']} 轮" if c.get("grouped") else ""
    return f"{name} · {timing}{group}"
