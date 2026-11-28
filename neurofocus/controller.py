from dataclasses import replace
from .engine import Engine, Entry
from . import config
from .modes import Profiles, LEGACY_FIELDS, from_settings


class Controller:
    """Application boundary; consumers can drive this without Qt."""
    def __init__(self, store, path, settings, clock, engine=None):
        self.store, self.path, self.settings = store, path, settings
        self.clock, self.engine = clock, engine or Engine()
        self.pending = []
        self.sid = None
        self.saved = 0
        self.closing_status = None
        self.tag_id = store.tags.selected()
        self.block = 0
        self.profiles = Profiles(store.db,settings)
        self._cycle_cache=None

    def select_tag(self, tag_id):
        if tag_id == self.tag_id:
            return []
        events = self.update("flush")
        self.store.tags.select(tag_id,self.sid,self.last_wall)
        self.tag_id = tag_id
        self.block += 1
        return events

    def configure(self, **changes):
        value = replace(self.settings, **changes)
        config.save(self.path, value)
        self.settings = value
        if any(k in LEGACY_FIELDS for k in changes): self.profiles.items['neuro']=from_settings(value)

    @property
    def selected_profile(self):
        return self.profiles.items[self.profiles.selected]

    def save_profile(self,profile):
        if profile.id=="neuro":
            self.configure(**{k:getattr(profile,k) for k in LEGACY_FIELDS})
        else:
            self.profiles.save(profile)

    def next_round(self,profile):
        if not profile.grouped: return 1
        key=(profile.id,profile.rounds,self.store.db.total_changes)
        if self._cycle_cache is None or self._cycle_cache[0]!=key:
            row=self.store.db.execute("SELECT next_round FROM cycle_cursor WHERE mode=?",(profile.id,)).fetchone()
            self._cycle_cache=(key,row[0] if row and row[0]<=profile.rounds else 1)
        return self._cycle_cache[1]

    def start(self):
        if self.sid is not None:
            return
        now, wall, _ = self.clock.sample()
        self._start_at(now,wall)

    def _start_at(self,now,wall):
        profile=self.selected_profile
        index=self.next_round(profile)
        self.sid=self.store.start(wall,profile,self.tag_id,index)
        self.engine.start(profile,now,index)
        self.block=0
        self.saved = now

    def _sync(self, now, wall):
        if self.sid is None:
            return
        self.store.checkpoint(self.sid, self.pending, wall, self.closing_status or "active", self.tag_id)
        self.pending.clear()
        self.saved = now
        if self.closing_status:
            self.sid, self.closing_status = None, None

    def update(self, action=None, *, minutes=None):
        now, wall, woke = self.clock.sample()
        self.last_wall=wall
        if self.sid is None:
            return []
        if action=='rest' and (type(minutes) is not int or not 1<=minutes<=180):
            raise ValueError('休息时间需在 1–180 分钟内')
        if self.closing_status:
            self._sync(now,self.pending[-1].at if self.pending else wall)
            return []
        previous = self.engine.last
        if woke and not self.engine.paused and self.engine.phase != 'ready':
            # A missed suspend broadcast has an ambiguous wall-time boundary.
            # Retain the last observed instant and wait for explicit resume.
            self.engine.last = now
            self.engine.paused = True
            self.pending.append(Entry("wake_pause",wall))
        was_paused = self.engine.paused
        entries = self.engine.tick(now, wall)
        if was_paused and not woke and now>previous:
            self.pending.append(Entry("paused_ms",wall-(now-previous),now-previous))
        for entry in entries:
            if entry.kind == "resume_focus":
                self.block += 1
            self.pending.append(replace(entry, block=self.block) if entry.kind == "focus" else entry)
        events = [x.kind for x in entries if not x.duration]
        stop=wall
        auto=False
        if self.engine.phase == "idle":
            self.closing_status = "ended" if self.engine.manual_early else "done"
            stop=entries[-1].at
            auto=self.engine.config.auto_next and action not in ('closed','ended','reset','suspend','pause','rest','skip_rest') and not woke
        elif action in ("ended", "reset", "closed"):
            self.engine.stop()
            self.closing_status = action
        elif self.engine.phase=='ready':
            if action=='begin_rest':
                kind=self.engine.config.rest(self.engine.round_index)
                self.engine.begin_rest(kind,getattr(self.engine.config,kind))
                self.pending.append(Entry(kind+'_start',wall))
                events.append(kind+'_start')
            elif action=='skip_rest':
                self.engine.stop()
                self.closing_status='done'
        elif action in ("pause", "suspend"):
            self.engine.paused = True
            if not was_paused: self.pending.append(Entry(action,wall))
        elif action=="rest" and self.engine.phase in ("focus","micro"):
            if self.engine.config.count_up and self.engine.actual:
                self.pending.append(Entry("flow_finish",wall))
            self.engine.manual_early=not self.engine.config.count_up
            self.engine.begin_rest("manual",minutes)
            self.pending.append(Entry('manual_plan',wall,minutes*60000))
            self.pending.append(Entry("manual_start",wall))
            events.append("manual_start")
        elif action=="skip_rest" and self.engine.phase in ("manual","short","long"):
            kind=self.engine.phase+"_end"
            self.pending.append(Entry(kind,wall))
            events.append(kind)
            self.engine.stop()
            self.closing_status="ended" if self.engine.manual_early else "done"
        elif action == "resume" and was_paused:
            self.engine.resume(now)
            self.block += 1
            if was_paused: self.pending.append(Entry("resume",wall))
        if self.closing_status:
            self.pending.append(Entry(self.closing_status,stop))
        if woke and was_paused and action != "resume":
            events.append("wake_pause")
        if self.closing_status or events or (action is not None) or (self.pending and now - self.saved >= 5000):
            self._sync(now, stop if self.closing_status else wall)
        if auto:
            # Small repaint delays belong to the new cycle; long unattended gaps await confirmation.
            delay=wall-stop
            if 0<=delay<=2000:
                self._start_at(now-delay,stop)
                events.append('auto_start')
                events.extend(self.update())
        return events
