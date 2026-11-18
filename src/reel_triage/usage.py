"""How full the Claude plan's 5-hour and weekly windows are, for the app's bars.

Two sources, the fresher wins (same rule as School Notes and the doom status
bar): the status bar's shared snapshot, which every running Claude Code session
updates, and the percentages that `reel-triage run` prints after each review.
"""

import json
import os
import re
import tempfile
import time
from pathlib import Path

_LOG = re.compile(r"\[five_hour (\d+)%, seven_day (\d+)%\]")
SAME_WINDOW_S = 60


def statusbar_path() -> Path:
    return Path(os.environ.get("DOOMBAR_RATELIMITS")
                or Path(tempfile.gettempdir()) / "mugshot_ratelimits_global.json")


def load_statusbar(path: Path | None = None) -> dict:
    """{"five_hour": {"used": 0.19, "resets_at": unix}, "seven_day": {...}}; missing ones left out."""
    try:
        data = json.loads((path or statusbar_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for name in ("five_hour", "seven_day"):
        w = data.get(name) if isinstance(data, dict) else None
        if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
            out[name] = {"used": w["used_percentage"] / 100, "resets_at": float(w.get("resets_at") or 0)}
    return out


def from_log_line(line: str) -> dict | None:
    """The windows from a 'reel-triage run' review line, or None."""
    m = _LOG.search(line)
    if not m:
        return None
    return {"five_hour": int(m.group(1)) / 100, "seven_day": int(m.group(2)) / 100}


def now_used(window: dict | None, now: float | None = None) -> float | None:
    """Fullness now: a window that has reset since the reading is empty."""
    if not window:
        return None
    resets = window.get("resets_at") or 0
    if resets and (now or time.time()) >= resets:
        return 0.0
    return max(0.0, min(1.0, window["used"]))


def merge(snapshot: dict, live: dict | None, live_at: float, now: float | None = None) -> dict:
    """Combine the status bar snapshot with the last live reading from a run.

    The live reading has no reset time, so it counts only while its window
    hasn't reset (judged by the snapshot's reset time) and when it is higher."""
    now = now or time.time()
    out = {}
    for name in ("five_hour", "seven_day"):
        snap = snapshot.get(name)
        used = now_used(snap, now)
        if live and name in live:
            resets = (snap or {}).get("resets_at") or 0
            window_s = 5 * 3600 if name == "five_hour" else 7 * 86400
            still_same = (live_at > resets - window_s) if resets else (now - live_at < window_s)
            if still_same and (used is None or live[name] > used):
                used = live[name]
        reset = (snap or {}).get("resets_at") or 0
        out[name] = {"known": used is not None, "used": used or 0.0,
                     "reset": time.strftime("resets %a %H:%M", time.localtime(reset)) if reset > now else ""}
    return out
