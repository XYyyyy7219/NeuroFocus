import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from tempfile import NamedTemporaryFile
import os


@dataclass(frozen=True)
class Settings:
    focus: int = 90
    long: int = 20
    low: int = 3
    high: int = 5
    micro: int = 10
    micro_on: bool = True
    auto_long: bool = True
    inclusive: bool = True
    audio: bool = True
    volume: int = 45
    voice: str = "木琴"
    dark: bool = False
    pinned: bool = False
    notify: bool = True
    tray: bool = True
    calendar_low: int = 30
    calendar_mid: int = 90
    calendar_high: int = 180

    def __post_init__(self):
        cuts=(self.calendar_low,self.calendar_mid,self.calendar_high)
        if any(type(n) is not int for n in cuts) or not 0<cuts[0]<cuts[1]<cuts[2]<=1440:
            raise ValueError("日历阈值须按升序排列，范围 1–1440 分钟")
        for name, bounds in LIMITS.items():
            value = getattr(self, name)
            if type(value) is not int or not bounds[0] <= value <= bounds[1]:
                raise ValueError(name)
        if self.low > self.high or self.voice not in VOICES:
            raise ValueError("设置值超出范围")
        for field in fields(self):
            if field.type is bool and type(getattr(self, field.name)) is not bool:
                raise ValueError(field.name)


LIMITS = {"focus": (1, 720), "long": (1, 180), "micro": (1, 300),
          "low": (1, 120), "high": (1, 120), "volume": (0, 100)}
VOICES = ("木琴", "柔钟", "纯音")


def load(path: Path):
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Settings(**{f.name: data[f.name] for f in fields(Settings) if f.name in data})


def save(path: Path, settings: Settings):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
        tmp = Path(out.name)
        try:
            json.dump(asdict(settings), out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        except BaseException:
            out.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
