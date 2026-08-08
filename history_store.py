from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from threading import Lock

from paths import data_dir as default_data_dir

_DAY_RE = re.compile(r"history-(\d{4}-\d{2}-\d{2})\.jsonl$")


@dataclass
class HistoryEntry:
    ts: str
    source: str
    result: str
    hit: int = 0
    miss: int = 0
    completion: int = 0
    cost_yuan: float = 0.0
    saved_yuan: float = 0.0
    note: str = ""


class HistoryStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self._dir = data_dir or default_data_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path_for(self, day: str) -> Path:
        return self._dir / f"history-{day}.jsonl"

    def append(self, entry: HistoryEntry) -> None:
        day = entry.ts[:10] if entry.ts else date.today().isoformat()
        path = self._path_for(day)
        line = json.dumps(asdict(entry), ensure_ascii=False)
        with self._lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def list_days(self) -> list[str]:
        days: list[str] = []
        for path in self._dir.glob("history-*.jsonl"):
            m = _DAY_RE.search(path.name)
            if m:
                days.append(m.group(1))
        today = date.today().isoformat()
        if today not in days:
            days.append(today)
        days.sort(reverse=True)
        return days

    def load_day(self, day: str) -> list[HistoryEntry]:
        path = self._path_for(day)
        if not path.exists():
            return []
        entries: list[HistoryEntry] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    entries.append(
                        HistoryEntry(
                            ts=str(raw.get("ts", "")),
                            source=str(raw.get("source", "")),
                            result=str(raw.get("result", "")),
                            hit=int(raw.get("hit", 0) or 0),
                            miss=int(raw.get("miss", 0) or 0),
                            completion=int(raw.get("completion", 0) or 0),
                            cost_yuan=float(raw.get("cost_yuan", 0) or 0),
                            saved_yuan=float(raw.get("saved_yuan", 0) or 0),
                            note=str(raw.get("note", "")),
                        )
                    )
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        entries.reverse()
        return entries

    def sum_day_cost(self, day: str | None = None) -> float:
        """Sum estimated cost_yuan for a day (default: today, local machine)."""
        target = day or date.today().isoformat()
        return sum(entry.cost_yuan for entry in self.load_day(target))


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
