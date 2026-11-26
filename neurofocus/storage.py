import csv
import sqlite3
from datetime import date, datetime, time, timedelta


METRICS = ("focus", "micro", "long", "micro_count", "completed")


def day_at(ms):
    return datetime.fromtimestamp(ms / 1000).date()


def buckets(entries):
    result = {}
    for entry in entries:
        at, duration = entry.at, entry.duration
        if entry.kind in ("micro_start", "complete"):
            row = result.setdefault(str(day_at(at)), [0] * 5)
            row[3 if entry.kind == "micro_start" else 4] += 1
        while duration:
            day = day_at(at)
            midnight = datetime.combine(day + timedelta(days=1), time())
            step = min(duration, round(midnight.timestamp() * 1000) - at)
            result.setdefault(str(day), [0] * 5)[METRICS.index(entry.kind)] += step
            at += step
            duration -= step
    return result


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
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
        with self.db:
            self.db.execute("UPDATE sessions SET status='interrupted' WHERE status='active'")

    def start(self, wall):
        with self.db:
            return self.db.execute("INSERT INTO sessions(started,updated,status) VALUES(?,?,'active')",
                                   (wall, wall)).lastrowid

    def checkpoint(self, sid, entries, wall, status="active"):
        rows = buckets(entries)
        with self.db:
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
        with open(path, "w", encoding="utf-8-sig", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["周期ID","开始时间","最后记录时间","状态","统计日期","实际专注秒","微休息秒",
                             "长休息秒","微休息次数","完成周期数"])
            for sid, start, end, status, day, focus, micro, long, count, completed in self.db.execute("""
                SELECT id,started,updated,status,day,focus,micro,long,micro_count,completed
                FROM sessions LEFT JOIN days ON id=sid ORDER BY id,day"""):
                fmt = lambda ms: datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="seconds")
                writer.writerow([sid, fmt(start), fmt(end), STATUS[status], day or str(day_at(start)),
                                 *[(n or 0)/1000 for n in (focus,micro,long)], count or 0, completed or 0])


STATUS = dict(active="进行中", done="已完成", ended="手动结束", reset="已重置",
              interrupted="异常中断", closed="退出保存")
