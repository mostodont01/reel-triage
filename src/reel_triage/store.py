"""On-disk store: one folder per reel under the data directory.

    <data>/reels/<code>/meta.json      link, caption, author, status, your pick
                        verdict.json   Claude's review
                        video.mp4, transcript.txt, frames/*.jpg

The data directory is ~/.local/share/reel-triage (REEL_TRIAGE_HOME overrides
it). It is private: never inside the repo.
"""

import json
import os
import time
from pathlib import Path

from . import ids

PICKS = ("want", "tried", "dismissed")  # what you decided in the feed


def default_root() -> Path:
    env = os.environ.get("REEL_TRIAGE_HOME")
    return Path(env) if env else Path.home() / ".local" / "share" / "reel-triage"


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else default_root()
        self.reels = self.root / "reels"
        self.reels.mkdir(parents=True, exist_ok=True)

    # --- reels ---------------------------------------------------------
    def path(self, code: str) -> Path:
        return self.reels / code

    def exists(self, code: str) -> bool:
        return (self.path(code) / "meta.json").is_file()

    IMPORT_FIELDS = ("saved_at", "caption", "author", "author_id", "hashtags", "collections")

    def add(self, code: str, source: str = "manual", **info) -> bool:
        """Queue a reel. Returns False if it was already known; then fields
        it doesn't have yet (saved_at, caption, ...) are filled in and
        collections are merged."""
        info = {k: v for k, v in info.items() if k in self.IMPORT_FIELDS and v}
        if self.exists(code):
            meta = self.get(code)
            changed = False
            for k, v in info.items():
                if k == "collections":
                    merged = list(dict.fromkeys((meta.get(k) or []) + v))
                    changed |= merged != meta.get(k)
                    meta[k] = merged
                elif not meta.get(k):
                    meta[k] = v
                    changed = True
            if changed:
                self.save(meta)
            return False
        self.path(code).mkdir(parents=True, exist_ok=True)
        self.save({
            "id": code,
            "url": ids.url(code),
            "added": int(time.time()),
            "saved_at": None,
            "source": source,
            "status": "new",  # new -> fetched | failed
            "pick": None,
            **info,
        })
        return True

    def get(self, code: str) -> dict:
        return json.loads((self.path(code) / "meta.json").read_text(encoding="utf-8"))

    def save(self, meta: dict) -> None:
        _write_json(self.path(meta["id"]) / "meta.json", meta)

    def update(self, code: str, **fields) -> dict:
        meta = self.get(code)
        meta.update(fields)
        self.save(meta)
        return meta

    def all(self) -> list[dict]:
        """Every reel, newest saved first."""
        metas = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in self.reels.glob("*/meta.json")
        ]
        metas.sort(key=lambda m: (m.get("saved_at") or m.get("added") or 0), reverse=True)
        return metas

    # --- verdicts -------------------------------------------------------
    def verdict(self, code: str) -> dict | None:
        path = self.path(code) / "verdict.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def set_verdict(self, code: str, verdict: dict) -> None:
        _write_json(self.path(code) / "verdict.json", verdict)

    def set_pick(self, code: str, pick: str | None) -> dict:
        if pick not in PICKS and pick is not None:
            raise ValueError(f"pick must be one of {PICKS} or None")
        return self.update(code, pick=pick)

    # --- queues ---------------------------------------------------------
    def to_fetch(self, everything: bool = False) -> list[dict]:
        """Reels to download: the ones the quick sort marked "deep" and the
        ones added by hand (everything=True: all queued reels)."""
        return [
            m for m in self.all()
            if m["status"] == "new" and (
                everything or m.get("source") == "manual"
                or (m.get("quick") or {}).get("verdict") == "deep")
        ]

    def to_review(self) -> list[dict]:
        return [m for m in self.all() if m["status"] == "fetched" and not self.verdict(m["id"])]

    # --- your setup (fed to the reviewer) -------------------------------
    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    def settings(self) -> dict:
        try:
            return json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def set_setting(self, key: str, value) -> None:
        data = self.settings()
        data[key] = value
        self.root.mkdir(parents=True, exist_ok=True)
        _write_json(self.settings_file, data)

    @property
    def context_file(self) -> Path:
        return self.root / "context.md"

    def context(self) -> str:
        f = self.context_file
        return f.read_text(encoding="utf-8") if f.is_file() else ""
