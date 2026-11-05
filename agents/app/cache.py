"""Small JSON cache used for the recommendations and research reports."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class JsonCache:
    def __init__(self, path: Path, ttl_seconds: float) -> None:
        self.path = path
        self.ttl = ttl_seconds
        self._mem: dict[str, tuple[float, Any]] = {}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _store(self, data: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data))
        except OSError:
            pass

    def get(self, key: str) -> Any | None:
        hit = self._mem.get(key)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        raw = self._load().get(key)
        if raw and time.time() - raw.get("t", 0) < self.ttl:
            self._mem[key] = (raw["t"], raw["v"])
            return raw["v"]
        return None

    def set(self, key: str, value: Any) -> None:
        self._mem[key] = (time.time(), value)
        data = self._load()
        data[key] = {"t": time.time(), "v": value}
        self._store(data)
