"""Import saved posts: Instagram's data export (zip, folder, JSON or HTML) or
any text file with links / shortcodes (one per line or space-separated).

read() returns {shortcode: info}; info may hold saved_at, caption, author,
author_id, hashtags and collections (your own Saved folders), whatever the
source knows.
"""

import json
import zipfile
from pathlib import Path

from . import ids


def fix_text(s: str) -> str:
    """Instagram exports write UTF-8 bytes as if they were Latin-1
    ("PoslednÃ­" instead of "Poslední"). Undo that when it applies."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


# --- Instagram's export format (2025-2026) ------------------------------
#   saved_posts.json: [ {"timestamp": ..., "label_values": [
#       {"label": "URL", "href": ...}, {"label": "Caption", "value": ...},
#       {"title": "Hashtags", "dict": [{"dict": [{"label": "Name", "value": "llm"}]}]},
#       {"title": "Owner", "dict": [{"dict": [{"label": "Name"...}, {"label": "Username"...}]}]}
#   ]} ]
#   saved_collections.json: [ {"label_values": [{"label": "Name", "value": "robotics"},
#       {"dict": [{"dict": [{"label": "URL", "href": ...}, ...]}]}]} ]
def _labels(items) -> dict:
    out = {}
    for lv in items or []:
        if isinstance(lv, dict) and lv.get("label"):
            out.setdefault(lv["label"], lv.get("href") or lv.get("value"))
    return out


def _post(label_values: list) -> tuple[str | None, dict]:
    flat = _labels(label_values)
    codes = ids.find_all(flat.get("URL") or "")
    if not codes:
        return None, {}
    info = {}
    if flat.get("Caption"):
        info["caption"] = fix_text(flat["Caption"]).strip()
    for lv in label_values:
        if not isinstance(lv, dict):
            continue
        if lv.get("title") == "Hashtags":
            tags = [_labels(d.get("dict")).get("Name") for d in lv.get("dict") or []]
            info["hashtags"] = [fix_text(t) for t in tags if t]
        elif lv.get("title") == "Owner":
            owner = _labels((lv.get("dict") or [{}])[0].get("dict"))
            if owner.get("Name"):
                info["author"] = fix_text(owner["Name"])
            if owner.get("Username"):
                info["author_id"] = owner["Username"]
    return codes[0], info


def _is_export(obj) -> bool:
    return isinstance(obj, list) and obj and isinstance(obj[0], dict) and "label_values" in obj[0]


def _from_export(obj: list, out: dict, collection_file: bool) -> None:
    for entry in obj:
        lvs = entry.get("label_values") or []
        if collection_file:
            name = _labels(lvs).get("Name")
            name = fix_text(name).strip() if name else None
            for lv in lvs:
                for item in (lv.get("dict") or []) if isinstance(lv, dict) else []:
                    code, info = _post(item.get("dict") or [])
                    if code:
                        rec = out.setdefault(code, {})
                        for k, v in info.items():
                            rec.setdefault(k, v)
                        if name and name not in rec.setdefault("collections", []):
                            rec["collections"].append(name)
        else:
            code, info = _post(lvs)
            if code:
                rec = out.setdefault(code, {})
                rec.update({k: v for k, v in info.items() if v})
                if isinstance(entry.get("timestamp"), int):
                    rec["saved_at"] = entry["timestamp"]


# --- anything else: walk for links ---------------------------------------
def _walk(obj, out: dict) -> None:
    if isinstance(obj, dict):
        href = obj.get("href") or obj.get("value")
        if isinstance(href, str):
            ts = obj.get("timestamp")
            for code in ids.find_all(href):
                rec = out.setdefault(code, {})
                if isinstance(ts, int) and ts > 0:
                    rec.setdefault("saved_at", ts)
        for value in obj.values():
            _walk(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _walk(value, out)
    elif isinstance(obj, str):
        for code in ids.find_all(obj):
            out.setdefault(code, {})


def _from_text(name: str, text: str, out: dict) -> None:
    if name.endswith(".json"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = None
        if obj is not None:
            if _is_export(obj):
                _from_export(obj, out, collection_file="collection" in name.lower())
            else:
                _walk(obj, out)
            return
    for code in ids.find_all(text):
        out.setdefault(code, {})
    if not name.endswith((".html", ".htm")):
        for word in text.split():
            if "instagram.com" not in word:
                code = ids.parse(word)
                if code:
                    out.setdefault(code, {})


def _is_saved(name: str) -> bool:
    """In a full export, only the saved-posts files matter (other files link
    to your own posts, liked posts etc.)."""
    lower = name.lower()
    return "saved" in lower and lower.endswith((".json", ".html", ".htm"))


def _order(names: list[str]) -> list[str]:
    """saved_posts before saved_collections (posts carry the timestamps)."""
    return sorted(names, key=lambda n: ("collection" in n.lower(), n))


def read(path: Path) -> dict[str, dict]:
    path = Path(path)
    out: dict[str, dict] = {}
    if path.is_dir():
        files = [p for p in path.rglob("*") if p.is_file() and _is_saved(str(p.relative_to(path)))]
        for name in _order([str(p) for p in files]):
            _from_text(Path(name).name, Path(name).read_text(encoding="utf-8", errors="replace"), out)
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for name in _order([n for n in z.namelist() if _is_saved(n)]):
                _from_text(Path(name).name, z.read(name).decode("utf-8", errors="replace"), out)
    else:
        _from_text(path.name, path.read_text(encoding="utf-8", errors="replace"), out)
    return out
