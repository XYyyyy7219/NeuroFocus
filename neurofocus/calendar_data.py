"""Read-only projections over focus_spans and days. All intervals include both dates."""
from calendar import monthrange
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
import json


def rolling(today, months):
    year, month0 = divmod(today.year*12+today.month-1-months,12)
    days = monthrange(year,month0+1)[1]
    return date(year,month0+1,min(days,today.day))+timedelta(days=1),today


def position(first, day):
    return ((day-first).days+first.weekday())//7,day.weekday()


def level(ms, cuts):
    return 0 if ms<=0 else 1+sum(ms>n*60000 for n in cuts)


@dataclass
class Day:
    tags: Counter = field(default_factory=Counter)
    ms: int = 0
    cycles: int = 0
    completed: int = 0
    micro: int = 0
    short_ms: int = 0
    long_ms: int = 0


class CalendarData:
    def __init__(self,db,first,last,today,selected=None):
        self.days={}
        self.tags=Counter()
        self.ms=self.completed=self.active=0
        end=min(last,today)
        self.elapsed=max(0,(end-first).days+1)
        if not self.elapsed or selected==set(): return
        args=(first.isoformat(),end.isoformat())
        tag_sql=""
        session_sql=""
        if selected is not None:
            # A single JSON parameter also works with very large tag selections.
            tag_sql=" AND tag IN (SELECT value FROM json_each(?))"
            session_sql=" AND sid IN (SELECT sid FROM focus_spans WHERE 1=1"+tag_sql+")"
            args+= (json.dumps(sorted(selected)),)
        for day,key,ms in db.execute("""SELECT day,tag,sum(ms) FROM focus_spans
                WHERE day BETWEEN ? AND ?"""+tag_sql+" GROUP BY day,tag",args):
            item=self.days.setdefault(date.fromisoformat(day),Day())
            item.tags[key]=ms
            item.ms+=ms
            self.tags[key]+=ms
            self.ms+=ms
        self.active=len(self.days)
        for day,count,done,events,short,long in db.execute("""SELECT day,count(*),
            sum(completed),sum(micro_count),sum(micro),sum(long) FROM days
            WHERE day BETWEEN ? AND ?"""+session_sql+" GROUP BY day",args):
            item=self.days.setdefault(date.fromisoformat(day),Day())
            item.cycles,item.completed,item.micro,item.short_ms,item.long_ms=count,done,events,short,long
            self.completed+=done

    @property
    def daily_mean(self):
        return self.ms/self.elapsed if self.elapsed else 0

    @property
    def active_mean(self):
        return self.ms/self.active if self.active else 0


def records(db,day,selected,page=0):
    args=[day.isoformat()]
    sql="SELECT sid,tag,started,ended,ms FROM focus_spans WHERE day=?"
    if selected is not None:
        sql+=" AND tag IN (SELECT value FROM json_each(?))"
        args.append(json.dumps(sorted(selected)))
    return list(db.execute(sql+" ORDER BY sid,block LIMIT 26 OFFSET ?",[*args,page*25]))
