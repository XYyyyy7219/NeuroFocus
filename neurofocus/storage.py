import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from datetime import date, datetime, time, timedelta
from .tags import Tags, migrate
from . import history


METRICS = ("focus", "micro", "long", "micro_count", "completed")


def day_at(ms):
    return datetime.fromtimestamp(ms / 1000).date()


def day_parts(at, duration):
    while duration:
        day = day_at(at)
        midnight = datetime.combine(day + timedelta(days=1), time())
        step = min(duration, round(midnight.timestamp() * 1000) - at)
        yield str(day), at, step
        at += step
        duration -= step


def buckets(entries):
    result = {}
    for entry in entries:
        at, duration = entry.at, entry.duration
        if entry.kind in ("micro_start", "complete"):
            row = result.setdefault(str(day_at(at)), [0] * 5)
            row[3 if entry.kind == "micro_start" else 4] += 1
        if entry.kind not in METRICS[:3]:
            continue
        for day, _, step in day_parts(at, duration):
            result.setdefault(day, [0] * 5)[METRICS.index(entry.kind)] += step
    return result


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        history.backup_if_needed(self.db,path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(
                id INTEGER PRIMARY KEY, started INTEGER NOT NULL,
                updated INTEGER NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS days(
                sid INTEGER NOT NULL REFERENCES sessions(id), day TEXT NOT NULL,
                focus INTEGER NOT NULL, micro INTEGER NOT NULL, long INTEGER NOT NULL,
                micro_count INTEGER NOT NULL, completed INTEGER NOT NULL,
                PRIMARY KEY(sid,day));
        """)
        migrate(self.db)
        history.install(self.db)
        self.tags = Tags(self.db)
        with self.db:
            self.db.execute("UPDATE sessions SET status='interrupted' WHERE status='active'")

    def start(self, wall, settings=None, tag=0):
        with self.db:
            sid = self.db.execute("INSERT INTO sessions(started,updated,status) VALUES(?,?,'active')",
                                   (wall, wall)).lastrowid
            if settings is not None:
                config = {k:getattr(settings,k) for k in ("focus","long","micro","low","high","micro_on","inclusive","auto_long")}
                self.db.execute("INSERT INTO session_protocol(sid,config) VALUES(?,?)",(sid,json.dumps(config)))
                self.db.execute("INSERT INTO study_events(sid,at,kind,tag) VALUES(?,?,'start',?)",(sid,wall,tag))
            return sid

    def checkpoint(self, sid, entries, wall, status="active", tag_id=0):
        rows = buckets(entries)
        with self.db:
            spans = {}
            self.db.executemany("INSERT INTO study_events(sid,at,kind,tag) VALUES(?,?,?,?)",
                ((sid,e.at,e.kind,tag_id) for e in entries if e.kind in history.EVENTS))
            paused = sum(e.duration for e in entries if e.kind=="paused_ms")
            if paused:
                self.db.execute("UPDATE session_protocol SET paused_ms=paused_ms+? WHERE sid=?",(paused,sid))
            for entry in entries:
                if entry.kind != "focus":
                    continue
                for day, at, step in day_parts(entry.at,entry.duration):
                    span = spans.setdefault((day,entry.block),[at,at,0])
                    span[1] = at+step
                    span[2] += step
            for (day,block),(start,end,ms) in spans.items():
                self.db.execute("""INSERT INTO focus_spans VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(sid,day,block,tag) DO UPDATE SET ended=excluded.ended,
                    ms=focus_spans.ms+excluded.ms""",(sid,day,block,tag_id,start,end,ms))
            for day, values in rows.items():
                self.db.execute("""INSERT INTO days VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(sid,day) DO UPDATE SET focus=focus+excluded.focus,
                    micro=micro+excluded.micro,long=long+excluded.long,
                    micro_count=micro_count+excluded.micro_count,completed=completed+excluded.completed""",
                                (sid, day, *values))
            self.db.execute("UPDATE sessions SET updated=?,status=? WHERE id=?", (wall, status, sid))

    def daily(self, start, end):
        return dict((row[0], row[1:]) for row in self.db.execute("""
          SELECT day,sum(focus),sum(micro),sum(long),sum(micro_count),sum(completed)
          FROM days WHERE day BETWEEN ? AND ? GROUP BY day ORDER BY day""", (str(start), str(end))))

    def history(self, limit=100, offset=0):
        return list(self.db.execute("""SELECT started,status,coalesce(sum(focus),0),
            coalesce(sum(micro),0),coalesce(sum(long),0),coalesce(sum(micro_count),0),
            coalesce(sum(completed),0) FROM sessions LEFT JOIN days ON sessions.id=sid
            GROUP BY sessions.id ORDER BY sessions.id DESC LIMIT ? OFFSET ?""", (limit, offset)))

    def export(self, path):
        headers = ["周期ID","开始时间","最后记录时间","状态","统计日期","实际专注秒",
                   "微休息秒","长休息秒","微休息次数","完成周期数","标签ID","标签名称","标签颜色"]
        if Path(path).suffix.lower() == ".json":
            segments = self.db.execute("""SELECT sid,day,block,tag,started,ended,ms
                FROM focus_spans ORDER BY sid,day,block""")
            names = [col[0] for col in segments.description]
            payload = dict(version=1,tags=[asdict(t) for t in self.tags.all()],
                records=[dict(zip(headers,row)) for row in self._export_rows()],
                focus_spans=[dict(zip(names,row)) for row in segments])
            Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(headers)
            writer.writerows(self._export_rows())

    def _export_rows(self):
        tags = {t.id:t for t in self.tags.all()}
        previous = None
        for sid,start,end,status,day,key,focus,micro,long,count,completed in self.db.execute("""
            WITH totals AS (SELECT sid,day,tag,sum(ms) AS ms FROM focus_spans GROUP BY sid,day,tag)
            SELECT s.id,s.started,s.updated,s.status,d.day,coalesce(t.tag,0),coalesce(t.ms,0),
                   d.micro,d.long,d.micro_count,d.completed
            FROM sessions s LEFT JOIN days d ON d.sid=s.id
            LEFT JOIN totals t ON t.sid=s.id AND t.day=d.day ORDER BY s.id,d.day,t.tag"""):
            if previous == (sid,day):
                micro,long,count,completed = 0,0,0,0
            previous = sid,day
            tag = tags[key]
            fmt = lambda ms: datetime.fromtimestamp(ms/1000).astimezone().isoformat(timespec="seconds")
            yield [sid,fmt(start),fmt(end),STATUS[status],day or str(day_at(start)),focus/1000,
                   (micro or 0)/1000,(long or 0)/1000,count or 0,completed or 0,key,tag.name,tag.color]


STATUS = dict(active="进行中", done="已完成", ended="手动结束", reset="已重置",
              interrupted="异常中断", closed="退出保存")
