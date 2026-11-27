"""SQLite-backed tag catalogue and reporting over actual focus intervals."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import re


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    color: str
    archived: bool


def migrate(db):
    with db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            return
        if version != 0:
            raise ValueError("学习数据库来自更高版本，请使用新版 NeuroFocus")
        db.execute("""CREATE TABLE tags(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            color TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL)""")
        db.execute("INSERT INTO tags VALUES(0,'未分类','#82968C',0,0)")
        db.execute("CREATE TABLE tag_choice(slot INTEGER PRIMARY KEY CHECK(slot=1), tag INTEGER NOT NULL REFERENCES tags)")
        db.execute("INSERT INTO tag_choice VALUES(1,0)")
        db.execute("""CREATE TABLE focus_spans(sid INTEGER NOT NULL REFERENCES sessions,
            day TEXT NOT NULL, block INTEGER NOT NULL, tag INTEGER NOT NULL REFERENCES tags,
            started INTEGER, ended INTEGER, ms INTEGER NOT NULL CHECK(ms>0),
            PRIMARY KEY(sid,day,block,tag))""")
        db.execute("CREATE INDEX span_by_day ON focus_spans(day,tag)")
        db.execute("CREATE INDEX span_by_tag ON focus_spans(tag,day)")
        # Old versions only know per-day totals. NULL times preserve that distinction.
        db.execute("""INSERT INTO focus_spans SELECT sid, day, -1, 0, NULL, NULL, focus
                      FROM days WHERE focus>0""")
        db.execute("PRAGMA user_version=1")


class Tags:
    def __init__(self, db):
        self.db = db

    def all(self):
        return [Tag(*row) for row in self.db.execute(
            "SELECT id,name,color,archived FROM tags ORDER BY position,id")]

    def save(self, name, color, tag_id=None):
        name = name.strip()
        if not name or not re.fullmatch(r"#[a-fA-F0-9]{6}", color):
            raise ValueError("请填写标签名称并选择有效颜色")
        if any(t.name.casefold() == name.casefold() and t.id != tag_id for t in self.all()):
            raise ValueError("已有同名标签（包括已归档标签）")
        with self.db:
            if tag_id is None:
                return self.db.execute("""INSERT INTO tags(name,color,position)
                    SELECT ?,?,max(position)+1 FROM tags""", (name,color)).lastrowid
            if not tag_id:
                raise ValueError("未分类是内置标签")
            self.db.execute("UPDATE tags SET name=?,color=? WHERE id=?", (name,color,tag_id))
        return tag_id

    def selected(self):
        return self.db.execute("SELECT tag FROM tag_choice").fetchone()[0]

    def select(self, key):
        with self.db:
            if not self.db.execute("SELECT 1 FROM tags WHERE id=? AND archived=0",(key,)).fetchone():
                raise ValueError("请选择使用中的标签")
            self.db.execute("UPDATE tag_choice SET tag=?", (key,))

    def archive(self, key, value):
        if not key:
            raise ValueError("未分类是内置标签")
        with self.db:
            if value:
                self.db.execute("UPDATE tag_choice SET tag=0 WHERE tag=?", (key,))
            self.db.execute("UPDATE tags SET archived=? WHERE id=?", (bool(value),key))

    def move(self, key, direction):
        ordered = [t.id for t in self.all() if t.id and not t.archived]
        index = ordered.index(key)
        other = index + direction
        if direction not in (-1,1) or not 0 <= other < len(ordered):
            return
        ordered[index], ordered[other] = ordered[other], ordered[index]
        # Keep positions unique across archived and active items.
        archived = [t.id for t in self.all() if t.archived]
        with self.db:
            self.db.executemany("UPDATE tags SET position=? WHERE id=?", enumerate(ordered+archived,1))

    def bounds(self, mode, today, custom=None):
        if mode == "自定义":
            start,end = custom
            if start > end:
                raise ValueError("开始日期须早于或等于结束日期")
            return start,end
        if mode == "全部":
            a,b = self.db.execute("SELECT min(day),max(day) FROM focus_spans").fetchone()
            return (date.fromisoformat(a),max(today,date.fromisoformat(b))) if a else (today,today)
        start = {"今日":today, "本周":today-timedelta(days=today.weekday()),
                 "本月":today.replace(day=1), "本年":today.replace(month=1,day=1)}[mode]
        return start,today

    def report(self,start,end):
        catalogue = {t.id:t for t in self.all()}
        daily = list(self.db.execute("""SELECT day,tag,sum(ms) FROM focus_spans
            WHERE day BETWEEN ? AND ? GROUP BY day,tag ORDER BY day,tag""",(str(start),str(end))))
        totals = defaultdict(int)
        for _,key,ms in daily:
            totals[key] += ms
        total = sum(totals.values())
        days = (end-start).days+1
        rows = [(catalogue[key],ms,ms/total,ms/days) for key,ms in
                sorted(totals.items(),key=lambda item:(-item[1],item[0]))]
        return rows,daily,total

    def history(self,key,start,end,limit,offset):
        return list(self.db.execute("""SELECT day,sid,started,ended,ms FROM focus_spans
            WHERE tag=? AND day BETWEEN ? AND ? ORDER BY day DESC,sid DESC,block DESC
            LIMIT ? OFFSET ?""",(key,str(start),str(end),limit,offset)))


def grouped_days(daily, mode):
    groups = defaultdict(dict)
    for day,key,ms in daily:
        d = date.fromisoformat(day)
        if mode == "周": d -= timedelta(days=d.weekday())
        if mode == "月": d = d.replace(day=1)
        values = groups[d]
        values[key] = values.get(key,0) + ms
    return sorted(groups.items())
