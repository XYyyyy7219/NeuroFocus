"""Time values are integer milliseconds. No GUI, OS or storage dependencies."""
from dataclasses import dataclass
from random import randint
from .config import Settings


@dataclass(frozen=True)
class Entry:
    kind: str
    at: int       # local calendar attribution uses this Unix millisecond timestamp
    duration: int = 0
    block: int = 0  # Controller assigns a number to each continuous focus stretch.


class Engine:
    def __init__(self, random_interval=randint):
        self.draw = random_interval
        self.config = Settings()
        self.phase = "idle"
        self.paused = False
        self.used = self.left = self.last = 0

    def start(self, config, now):
        if self.phase != "idle":
            raise ValueError("已有进行中的周期")
        self.config = config
        self.used = 0
        self.paused = False
        self.last = now
        self._focus()

    @property
    def target(self):
        return self.config.focus * 60_000

    def _focus(self):
        self.phase = "focus"
        self.left = (self.draw(self.config.low * 60_000, self.config.high * 60_000)
                     if self.config.micro_on else self.target)

    def stop(self):
        self.phase = "idle"
        self.paused = False

    def remaining(self):
        if self.phase == "focus":
            return self.target - self.used
        if self.phase == "micro" and self.config.inclusive:
            return min(self.left, self.target - self.used)
        return self.left

    def tick(self, now, wall):
        elapsed = now - self.last
        if elapsed < 0:
            raise ValueError("单调时钟倒退")
        self.last = now
        entries = []
        if self.paused:
            return entries
        cursor = wall - elapsed
        while elapsed and self.phase != "idle":
            counts = self.phase == "focus" or (self.phase == "micro" and self.config.inclusive)
            step = min(elapsed, self.left, self.target - self.used if counts else self.left)
            entries.append(Entry(self.phase, cursor, step))
            self.left -= step
            if counts:
                self.used += step
            elapsed -= step
            cursor += step
            if counts and self.used == self.target:
                entries.append(Entry("complete", cursor))
                if self.config.auto_long:
                    self.phase = "long"
                    self.left = self.config.long * 60_000
                    entries.append(Entry("long_start", cursor))
                else:
                    self.stop()
            elif self.left == 0:
                if self.phase == "focus":
                    self.phase = "micro"
                    self.left = self.config.micro * 1000
                    entries.append(Entry("micro_start", cursor))
                elif self.phase == "micro":
                    self._focus()
                    entries.append(Entry("resume_focus", cursor))
                else:
                    self.stop()
                    entries.append(Entry("long_end", cursor))
        return entries

    def pause(self, now, wall):
        entries = self.tick(now, wall)
        self.paused = self.phase != "idle"
        return entries

    def resume(self, now):
        if self.paused:
            self.last = now
            self.paused = False
