from dataclasses import replace
from .engine import Engine
from . import config


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

    def select_tag(self, tag_id):
        if tag_id == self.tag_id:
            return []
        events = self.update("flush")
        self.store.tags.select(tag_id)
        self.tag_id = tag_id
        self.block += 1
        return events

    def configure(self, **changes):
        value = replace(self.settings, **changes)
        config.save(self.path, value)
        self.settings = value

    def start(self):
        if self.sid is not None:
            return
        now, wall, _ = self.clock.sample()
        self.sid = self.store.start(wall)
        self.engine.start(self.settings, now)
        self.saved = now

    def _sync(self, now, wall):
        if self.sid is None:
            return
        self.store.checkpoint(self.sid, self.pending, wall, self.closing_status or "active", self.tag_id)
        self.pending.clear()
        self.saved = now
        if self.closing_status:
            self.sid, self.closing_status = None, None

    def update(self, action=None):
        now, wall, woke = self.clock.sample()
        if self.sid is None:
            return []
        if self.closing_status:
            self._sync(now, wall)
            return []
        if woke and not self.engine.paused:
            # A missed suspend broadcast has an ambiguous wall-time boundary.
            # Retain the last observed instant and wait for explicit resume.
            self.engine.last = now
            self.engine.paused = True
        was_paused = self.engine.paused
        entries = self.engine.tick(now, wall)
        for entry in entries:
            if entry.kind == "resume_focus":
                self.block += 1
            self.pending.append(replace(entry, block=self.block) if entry.kind == "focus" else entry)
        events = [x.kind for x in entries if not x.duration]
        if self.engine.phase == "idle":
            self.closing_status = "done"
        elif action in ("ended", "reset", "closed"):
            self.engine.stop()
            self.closing_status = action
        elif action in ("pause", "suspend"):
            self.engine.paused = True
        elif action == "resume":
            self.engine.resume(now)
            self.block += 1
        if woke and was_paused and action != "resume":
            events.append("wake_pause")
        if self.closing_status or events or (action is not None) or (self.pending and now - self.saved >= 5000):
            self._sync(now, wall)
        return events
