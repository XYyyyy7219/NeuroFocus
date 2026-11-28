"""Local history projections. Durations originate exclusively in the timer ledger."""
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from time import time_ns
from .modes import snapshot_title

FIELDS = ("topic", "gain", "question", "next_step", "experience")
TITLES = ("学习主题", "学习收获", "疑问与思考", "下一步", "学习体验")
EVENTS = {"start":"开始专注", "micro_start":"进入微休息", "resume_focus":"结束微休息",
          "complete":"完成专注", "long_start":"进入长休息", "long_end":"结束长休息",
          "pause":"暂停", "suspend":"系统挂起", "wake_pause":"唤醒后暂停",
          "resume":"继续", "tag":"切换标签", "ended":"提前结束", "reset":"重置",
          "closed":"关闭程序", "done":"周期结束"}


EVENTS.update(short_start="进入短休息",short_end="短休息结束",manual_start="主动进入休息",
              manual_end="自主休息结束",rest_hint="温和休息提醒",flow_finish="结束自由专注段")


def backup_if_needed(db, path):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "sessions" in tables and ("journal" not in tables or "rest_days" not in tables) and str(path) != ":memory:":
        stage="archive" if "journal" not in tables else "focus-engine"
        dest = Path(path).with_name(f"study-before-{stage}-{time_ns()}.sqlite3")
        with sqlite3.connect(dest) as backup:
            db.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("学习档案升级备份未通过检查")
        backup.close()


def install(db):
    with db:
        db.execute("BEGIN")
        db.execute("CREATE TABLE IF NOT EXISTS focus_profiles(id TEXT PRIMARY KEY, config TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS focus_selected(slot INTEGER PRIMARY KEY, mode TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS manual_rest_plan(sid INTEGER PRIMARY KEY REFERENCES sessions,minutes INTEGER NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS rest_days(sid INTEGER REFERENCES sessions,day TEXT,
            kind TEXT CHECK(kind IN ('short','manual')),ms INTEGER NOT NULL,PRIMARY KEY(sid,day,kind))""")
        db.execute("""CREATE TABLE IF NOT EXISTS cycle_cursor(mode TEXT PRIMARY KEY, next_round INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS session_protocol(
            sid INTEGER PRIMARY KEY REFERENCES sessions, config TEXT NOT NULL, paused_ms INTEGER DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS study_events(
            id INTEGER PRIMARY KEY, sid INTEGER NOT NULL REFERENCES sessions, at INTEGER NOT NULL,
            kind TEXT NOT NULL, tag INTEGER REFERENCES tags)""")
        db.execute("CREATE INDEX IF NOT EXISTS event_session ON study_events(sid,id)")
        db.execute("""CREATE TABLE IF NOT EXISTS journal(
            sid INTEGER, day TEXT, block INTEGER, tag INTEGER, topic TEXT NOT NULL,
            gain TEXT NOT NULL, question TEXT NOT NULL, next_step TEXT NOT NULL, experience TEXT NOT NULL,
            updated INTEGER NOT NULL, PRIMARY KEY(sid,day,block,tag),
            FOREIGN KEY(sid,day,block,tag) REFERENCES focus_spans(sid,day,block,tag))""")


@dataclass
class Activity:
    key: tuple
    started: int | None
    ended: int | None
    ms: int = 0
    spans: list = field(default_factory=list)
    note: tuple = ("", "", "", "", "")
    mode_name: str = "旧版记录"

    @property
    def day(self): return self.key[1]

    @property
    def tag(self): return self.key[3]

    def matches(self, query):
        return not query or any(query.casefold() in v.casefold() for v in self.note)


def activities(db, sid=None):
    where = "" if sid is None else " WHERE f.sid=?"
    rows = db.execute("""SELECT f.sid,f.day,f.block,f.tag,f.started,f.ended,f.ms,
          coalesce(json_extract(p.config,'$.name'),'旧版记录'),j.topic,j.gain,j.question,j.next_step,j.experience FROM focus_spans f
          LEFT JOIN journal j USING(sid,day,block,tag) LEFT JOIN session_protocol p ON p.sid=f.sid""" + where +
          " ORDER BY f.sid,f.day,f.block,f.tag", () if sid is None else (sid,))
    result = []
    for session,day,block,tag,start,end,ms,mode,*note in rows:
        if not result or (session,day,tag) != (item.key[0],item.day,item.tag):
            item = Activity((session,day,block,tag),start,end,mode_name=mode)
            result.append(item)
            if note[0] is not None:
                item.note = tuple(note)
        item.ms += ms
        item.ended = end
        item.spans.append((start,end,ms))
    return result


def save_note(db, key, values):
    with db:
        if any(v.strip() for v in values):
            db.execute("""INSERT INTO journal VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(sid,day,block,tag) DO UPDATE SET topic=excluded.topic,
                gain=excluded.gain,question=excluded.question,next_step=excluded.next_step,
                experience=excluded.experience,updated=excluded.updated""",
                (*key,*values,time_ns()//1_000_000))
        else:
            db.execute("DELETE FROM journal WHERE sid=? AND day=? AND block=? AND tag=?", key)


def wall_time(ms):
    return "旧版日汇总" if ms is None else datetime.fromtimestamp(ms/1000).strftime("%H:%M:%S")


def session_detail(db, activity):
    sid = activity.key[0]
    counts = db.execute("SELECT sum(micro_count),sum(micro),sum(long) FROM days WHERE sid=?", (sid,)).fetchone()
    lines = [f"周期 {sid}　微休息 {counts[0] or 0} 次 / {(counts[1] or 0)/1000:g} 秒　长休息 {(counts[2] or 0)/1000:g} 秒"]
    protocol = db.execute("SELECT config,paused_ms FROM session_protocol WHERE sid=?", (sid,)).fetchone()
    extra=dict(db.execute("SELECT kind,sum(ms) FROM rest_days WHERE sid=? GROUP BY kind",(sid,)))
    lines.append(f"周期短休息 {extra.get('short',0)/1000:g} 秒　自主休息 {extra.get('manual',0)/1000:g} 秒")
    plan=db.execute('SELECT minutes FROM manual_rest_plan WHERE sid=?',(sid,)).fetchone()
    if plan: lines.append(f'主动选择的休息时间 {plan[0]} 分钟')
    if protocol:
        c = json.loads(protocol[0])
        lines.append(snapshot_title(protocol[0]))
        lines.append(f"长休息设置 {c['long']} 分钟，已记录暂停 {protocol[1]/1000:g} 秒")
        if c.get("short_on"): lines.append(f"短休息设置 {c['short']} 分钟")
        if c.get("count_up"):
            if c.get("suggest"):
                lines.append("四档休息建议（分钟）："+" / ".join(str(n) for n in c["break_steps"]))
            if c.get("reminder"): lines.append(f"休息提醒间隔 {c['reminder']} 分钟")
        lines.append((f"微休息间隔 {c['low']}–{c['high']} 分钟，每次 {c['micro']} 秒"
                      + ("，计入周期" if c['inclusive'] else "，独立计时")) if c['micro_on'] else "连续专注模式")
        if not c.get("count_up"): lines.append("到点进入休息" if c["auto_long"] else "到点等待")
        lines.append("自动开始下一轮" if c.get("auto_next") else "手动开始下一轮")
    else:
        lines.append("此周期没有配置、暂停或完整事件快照。")
    lines.append("当前活动的有效学习片段")
    lines.extend(f"{wall_time(a)} — {wall_time(b)}　{ms/1000:g} 秒" for a,b,ms in activity.spans)
    lines.append("周期事件")
    lines.extend(f"{wall_time(at)}　{EVENTS.get(k,k)}　{name or ''}" for at,k,name in db.execute(
        "SELECT at,kind,name FROM study_events LEFT JOIN tags ON tags.id=study_events.tag WHERE sid=? ORDER BY study_events.id",(sid,)))
    return "\n".join(lines)


def markdown(a, tag):
    header = f"# {a.note[0] or tag}\n\n{a.day} · {tag} · {a.ms/1000:g} 秒\n"
    return header + a.mode_name+"\n" + "".join(f"\n## {title}\n\n{value}\n" for title,value in zip(TITLES[1:],a.note[1:]) if value)
