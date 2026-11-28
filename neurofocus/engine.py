"""Time values are integer milliseconds. No GUI, OS or storage dependencies."""
from dataclasses import dataclass
from random import randint
from .modes import Profile, from_settings


@dataclass(frozen=True)
class Entry:
    kind: str
    at: int       # local calendar attribution uses this Unix millisecond timestamp
    duration: int = 0
    block: int = 0  # Controller assigns a number to each continuous focus stretch.


class Engine:
    def __init__(self, random_interval=randint):
        self.draw = random_interval
        self.config = Profile()
        self.round_index = 1
        self.actual = self.rest_total = 0
        self.manual_early = False
        self.next_reminder = 0
        self.phase = "idle"
        self.paused = False
        self.used = self.left = self.last = 0

    def start(self, config, now, round_index=1):
        if self.phase != "idle":
            raise ValueError("已有进行中的周期")
        self.config = config if isinstance(config,Profile) else from_settings(config)
        self.round_index = round_index
        self.manual_early = False
        self.actual = self.used = self.rest_total = 0
        self.next_reminder = self.config.reminder*60000
        self.paused = False
        self.last = now
        self._focus()

    @property
    def target(self):
        return self.config.focus * 60_000

    def _focus(self):
        self.phase = "focus"
        self.left = (self.draw(self.config.low * 60_000, self.config.high * 60_000)
                     if self.config.micro_on else None)

    def begin_rest(self, kind, minutes):
        self.phase = kind
        self.paused = False
        self.rest_total = self.left = minutes * 60000

    def stop(self):
        self.phase = "idle"
        self.paused = False

    def remaining(self):
        if self.phase == "focus":
            return self.actual if self.config.count_up else self.target - self.used
        if self.phase == "micro" and self.config.inclusive and not self.config.count_up:
            return min(self.left, self.target - self.used)
        return self.left

    def tick(self, now, wall):
        elapsed = now - self.last
        if elapsed < 0:
            raise ValueError("单调时钟倒退")
        self.last = now
        entries = []
        if self.paused or self.phase=='ready':
            return entries
        cursor = wall - elapsed
        while elapsed and self.phase not in ("idle","ready"):
            counts = self.phase == "focus" or (self.phase == "micro" and self.config.inclusive)
            step = min(elapsed,self.left) if self.left is not None else elapsed
            if counts and not self.config.count_up: step=min(step,self.target-self.used)
            if self.phase=="focus" and self.next_reminder: step=min(step,self.next_reminder-self.actual)
            entries.append(Entry(self.phase, cursor, step))
            if self.left is not None: self.left -= step
            if self.phase=="focus": self.actual += step
            if counts:
                self.used += step
            elapsed -= step
            cursor += step
            if self.next_reminder and self.actual==self.next_reminder:
                entries.append(Entry("rest_hint",cursor))
                self.next_reminder+=self.config.reminder*60000
            if counts and not self.config.count_up and self.used == self.target:
                entries.append(Entry("complete", cursor))
                if self.config.auto_long:
                    kind=self.config.rest(self.round_index)
                    self.begin_rest(kind,getattr(self.config,kind))
                    entries.append(Entry(kind+"_start", cursor))
                elif self.config.id=='neuro':
                    self.stop()
                else:
                    self.phase='ready'
                    self.left=getattr(self.config,self.config.rest(self.round_index))*60000
            elif self.left == 0:
                if self.phase == "focus":
                    self.phase = "micro"
                    self.left = self.config.micro * 1000
                    entries.append(Entry("micro_start", cursor))
                elif self.phase == "micro":
                    self._focus()
                    entries.append(Entry("resume_focus", cursor))
                else:
                    entries.append(Entry(self.phase+"_end", cursor))
                    self.stop()
        return entries

    def pause(self, now, wall):
        entries = self.tick(now, wall)
        self.paused = self.phase != "idle"
        return entries

    def resume(self, now):
        if self.paused:
            self.last = now
            self.paused = False
