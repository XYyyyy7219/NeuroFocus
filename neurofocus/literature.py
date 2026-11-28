"""Local reading collection. The public catalog is immutable; private edits are atomic."""
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from random import SystemRandom
from tempfile import NamedTemporaryFile
import json
import os
import re
import unicodedata

CATALOG = Path(__file__).with_name("literary_catalog.json")
SCENES = {"home", "focus", "starMap"}
PERIODS = (("少年与理想", "宁静与自然"), ("星辰与求知", "少年与理想"),
           ("哲思与人生", "宁静与自然"), ("宁静与自然", "温柔与悲悯"))


def string(value, limit=160, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not value.strip() and not empty):
        raise ValueError("文字字段缺失或过长")
    return value.strip()


def names(value):
    if not isinstance(value, (list, tuple)) or len(value) > 40:
        raise ValueError("类别、标签及场景须使用列表")
    return tuple(dict.fromkeys(string(x) for x in value))


@dataclass(frozen=True)
class Source:
    author: str
    book: str
    volume: int | None = None
    volumeTitle: str = ""
    chapter: str = ""
    section: str = ""
    lineStart: int | None = None
    lineEnd: int | None = None

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise ValueError("需要注明作者和作品")
        strings = {k: string(data.get(k, ""), empty=True) for k in ("volumeTitle", "chapter", "section")}
        nums = {k: data.get(k) for k in ("volume", "lineStart", "lineEnd")}
        if any(v is not None and (type(v) is not int or v < 1) for v in nums.values()):
            raise ValueError("卷数及行号须为正整数")
        lo, hi = nums["lineStart"], nums["lineEnd"]
        if (lo is None) != (hi is None) or (lo is not None and hi < lo):
            raise ValueError("请检查起止行号")
        return cls(string(data.get("author")), string(data.get("book")), nums['volume'],
                   strings['volumeTitle'], strings['chapter'], strings['section'], lo, hi)

    def credit(self, detailed=False):
        parts = [self.author, self.book]
        if self.volume:
            parts.append(f"卷 {self.volume}" + (f" · {self.volumeTitle}" if self.volumeTitle else ""))
        if detailed:
            parts.extend(filter(None, (self.chapter, self.section)))
            if self.lineStart:
                parts.append(f"第 {self.lineStart}–{self.lineEnd} 行")
        return "  ·  ".join(parts)


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    text: str | None
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    source: Source
    scenes: tuple[str, ...]
    enabled: bool
    reviewed: bool
    favorite: bool = False

    @classmethod
    def parse(cls, row):
        if not isinstance(row, dict):
            raise ValueError("条目应是对象")
        key = string(row.get("id"), 90)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", key):
            raise ValueError("ID 仅支持字母、数字、短横线、下划线或点")
        value = row.get("text")
        body = None if value is None else string(value, 6000, empty=True) or None
        categories = names(row.get("categories", [row["category"]] if "category" in row else []))
        scenes = names(row.get("scenes", ["home"]))
        if not categories or not scenes or not set(scenes) <= SCENES:
            raise ValueError("需要至少一个类别和有效的展示场景")
        enabled, reviewed, favorite = (row.get("enabled", bool(body)), row.get("reviewed", False), row.get("favorite", False))
        if any(type(v) is not bool for v in (enabled, reviewed, favorite)):
            raise ValueError("启用、审核与收藏须为布尔值")
        if enabled and not body:
            raise ValueError("空索引须先填写正文再启用")
        return cls(key, string(row.get("title")), body, categories, names(row.get("tags", [])),
                   Source.parse(row.get("source")), scenes, enabled, reviewed, favorite)


def read_json(path: Path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("文案文件超过 16 MiB")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
        tmp = Path(out.name)
        try:
            json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
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


def parse_bundle(data) -> dict[str, Entry]:
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("需要 version 为 1 且含 entries 列表的 JSON")
    entries = {}
    for row in data["entries"]:
        item = Entry.parse(row)
        if item.id in entries:
            raise ValueError(f"同一文件中 ID 重复：{item.id}")
        entries[item.id] = item
    return entries


def unique_text(items: Sequence[Entry]):
    seen: dict[str, str] = {}
    for item in items:
        if not item.text:
            continue
        normalized = "".join(unicodedata.normalize("NFKC", item.text).casefold().split())
        if normalized in seen:
            raise ValueError(f"正文与 {seen[normalized]} 重复：{item.id}")
        seen[normalized] = item.id


class Library:
    def __init__(self, path: Path):
        self.path = path
        self.base = parse_bundle(read_json(CATALOG))
        self.entries = self.base.copy()
        self.picks: dict[str, tuple[str, str]] = {}
        self.recent: list[str] = []
        self.problem = ""
        self.random = SystemRandom()
        if path.exists():
            try:
                state = read_json(path)
                entries = self.merge(parse_bundle(state))
                recent = state.get("recent", [])
                picks = state.get("picks", {})
                if not isinstance(recent, list) or not all(isinstance(x, str) for x in recent):
                    raise ValueError("展示历史格式错误")
                if not isinstance(picks, dict) or not all(k in SCENES and isinstance(v, list) and len(v)==2
                        and all(isinstance(x, str) for x in v) for k,v in picks.items()):
                    raise ValueError("场景记录格式错误")
                self.entries = entries
                self.picks = {k:(v[0],v[1]) for k,v in picks.items()}
                self.recent = recent[-16:]
            except (ValueError, OSError, RecursionError) as exc:
                self.problem = f"本地文案库暂不可读，已保留原文件。{exc}"

    def merge(self, incoming: dict[str, Entry]) -> dict[str, Entry]:
        merged = self.entries.copy()
        for key, item in incoming.items():
            original = self.base.get(key)
            old = merged.get(key)
            if original and replace(item, text=original.text, enabled=original.enabled,
                                    favorite=original.favorite) != original:
                raise ValueError(f"内置索引的来源与分类不能覆盖：{key}")
            if original and original.text and original.text != item.text:
                raise ValueError(f"内置原创示例的正文不能覆盖：{key}")
            if old and old.source != item.source:
                raise ValueError(f"ID 已属于其他出处：{key}")
            merged[key] = item
        unique_text(list(merged.values()))
        return merged

    def commit(self, entries, picks, recent):
        if self.problem:
            raise ValueError(self.problem)
        state = {"version":1, "entries":[asdict(v) for k,v in entries.items() if self.base.get(k)!=v],
                 "picks":picks, "recent":recent}
        atomic_json(self.path, state)
        self.entries, self.picks, self.recent = entries, picks, recent

    def import_bundle(self, data):
        incoming = parse_bundle(data)
        merged = self.merge(incoming)
        self.commit(merged, self.picks, self.recent)
        return len(incoming)

    def edit(self, key, **changes):
        row = asdict(self.entries[key])
        row.update(changes)
        self.import_bundle({"version":1, "entries":[row]})

    def export(self, path):
        if self.problem:
            raise ValueError(self.problem)
        atomic_json(path, {"version":1, "entries":[asdict(v) for v in self.entries.values()]})

    def choose(self, scene: str, now: datetime, *, period: str | None = None, another=False) -> Entry | None:
        if scene not in SCENES:
            raise ValueError("未知场景")
        token = period or now.date().isoformat()
        old_token, old_id = self.picks.get(scene, ("", ""))
        old = self.entries.get(old_id)
        if old_token == token and not another and old and old.enabled and old.text and scene in old.scenes:
            return old
        options = [x for x in self.entries.values() if x.text and x.enabled and scene in x.scenes]
        if not options:
            return None
        if len(options)>1 and (another or old_token!=token):
            options = [x for x in options if x.id != old_id] or options
        # Use the freshest eligible group, then prefer categories for the scene and time.
        unseen = [x for x in options if x.id not in self.recent]
        if unseen:
            options = unseen
        else:
            ranks = {k:i for i,k in enumerate(self.recent)}
            oldest = min(ranks[x.id] for x in options)
            options = [x for x in options if ranks[x.id]==oldest]
        hour = now.hour
        band = 0 if 5<=hour<10 else 1 if 10<=hour<17 else 2 if 17<=hour<20 else 3
        favored = {"星辰与求知","苍凉与史诗"} if scene=="starMap" else {"星辰与求知","宁静与自然"} if scene=="focus" else set(PERIODS[band])
        chosen = self.random.choice([x for x in options if favored.intersection(x.categories)] or options)
        recent = [k for k in self.recent if k!=chosen.id][-15:] + [chosen.id]
        picks = {**self.picks, scene:(token,chosen.id)}
        if self.problem:
            self.picks, self.recent = picks, recent
        else:
            self.commit(self.entries, picks, recent)
        return chosen


def excerpt_lines(path: Path, source: Source) -> str:
    """Read one user-selected file locally and offer only the indexed range for selection."""
    if source.lineStart is None or source.lineEnd is None:
        raise ValueError("该索引没有行号")
    if path.stat().st_size > 32*1024*1024:
        raise ValueError("TXT 超过 32 MiB，请直接粘贴选定的段落")
    raw = path.read_bytes()
    encodings = ("utf-16",) if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else ("utf-8-sig","gb18030")
    for enc in encodings:
        try:
            lines = raw.decode(enc).splitlines()
            break
        except UnicodeError:
            continue
    else:
        raise ValueError("无法识别 TXT 编码，请手动粘贴")
    if source.lineEnd > len(lines):
        raise ValueError("行号超出此版本范围，请核对版本或手动粘贴")
    return "\n".join(lines[source.lineStart-1:source.lineEnd])
