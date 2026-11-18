"""What the feed shows: verdict keys, filters, sorting and counts.

Pure functions over the reel dicts from server.reels_json(), shared by the
desktop app (the web feed has the same rules in JavaScript).
"""

VERDICTS = [("", "All"), ("try", "Try"), ("keep", "Keep"), ("maybe", "Maybe"),
            ("check", "To check"), ("skip", "Skip")]
ORDER = {"try": 0, "keep": 1, "maybe": 2, "check": 3, "wait": 4, "fail": 5, "skip": 6}
LABEL = {"try": "Try", "keep": "Keep", "maybe": "Maybe", "skip": "Skip",
         "check": "To check", "wait": "Not sorted", "fail": "Failed"}
PICK_LABEL = {"want": "Implement", "tried": "Tried", "dismissed": "Dismissed"}
PICK_FILTERS = [("", "Any"), ("want", "To implement"), ("tried", "Tried"),
                ("dismissed", "Dismissed"), ("none", "Not picked")]


def vkey(r: dict) -> str:
    """try / keep / maybe / skip (full review), check (worth a full review),
    wait (not sorted yet) or fail (download failed)."""
    if r.get("verdict"):
        return r["verdict"]["verdict"]
    if r.get("status") == "failed":
        return "fail"
    quick = r.get("quick")
    if quick:
        return {"deep": "check", "keep": "keep", "skip": "skip"}.get(quick.get("verdict"), "wait")
    return "wait"


def category(r: dict) -> str:
    return (r.get("verdict") or {}).get("category") or (r.get("quick") or {}).get("category") or ""


def title(r: dict) -> str:
    v, q = r.get("verdict") or {}, r.get("quick") or {}
    if v.get("title") or q.get("title"):
        return v.get("title") or q.get("title")
    return ((r.get("caption") or r["id"]).strip().split("\n")[0])[:90]


def _haystack(r: dict) -> str:
    v, q = r.get("verdict") or {}, r.get("quick") or {}
    parts = [r.get("author"), r.get("author_id"), r.get("caption"), v.get("title"), v.get("comment"),
             v.get("summary"), (v.get("tool") or {}).get("name"), " ".join(v.get("projects") or []),
             q.get("title"), q.get("note"), " ".join(r.get("collections") or [])]
    return " ".join(p for p in parts if p).lower()


def matches(r: dict, verdict: str = "", cat: str = "", pick: str = "", query: str = "") -> bool:
    k = vkey(r)
    if verdict and not (k in ("check", "wait", "fail") if verdict == "check" else k == verdict):
        return False
    if cat and category(r) != cat:
        return False
    if pick == "none":
        if r.get("pick"):
            return False
    elif pick and r.get("pick") != pick:
        return False
    if query and query.lower() not in _haystack(r):
        return False
    return True


def _time(r: dict) -> float:
    return r.get("saved_at") or r.get("added") or 0


def ordered(reels: list[dict], mode: str = "best") -> list[dict]:
    """best: reviewed first, by verdict and quality (skips last); new: newest saves first."""
    if mode == "new":
        return sorted(reels, key=lambda r: -_time(r))

    def rank(r):
        k = vkey(r)
        quality = (r.get("verdict") or {}).get("quality") or 0
        return ((0 if r.get("verdict") else 10) + ORDER.get(k, 9) + (20 if k == "skip" else 0),
                -quality, -_time(r))

    return sorted(reels, key=rank)


def counts(reels: list[dict]) -> dict:
    c = {k: 0 for k in ORDER}
    for r in reels:
        c[vkey(r)] = c.get(vkey(r), 0) + 1
    out = {"": len(reels), "try": c["try"], "keep": c["keep"], "maybe": c["maybe"],
           "check": c["check"] + c["wait"] + c["fail"], "skip": c["skip"]}
    for p in PICK_LABEL:
        out["pick:" + p] = sum(1 for r in reels if r.get("pick") == p)
    out["pick:none"] = sum(1 for r in reels if not r.get("pick"))
    out["pick:"] = len(reels)
    return out


def categories(reels: list[dict]) -> list[tuple[str, int]]:
    seen: dict[str, int] = {}
    for r in reels:
        c = category(r)
        if c:
            seen[c] = seen.get(c, 0) + 1
    return sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))


def frame_time(name: str) -> float | None:
    """Seconds from a frame file name like 'frames/02_012.3s.jpg'."""
    stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if "_" not in stem or not stem.endswith("s"):
        return None
    try:
        return float(stem.split("_", 1)[1][:-1])
    except ValueError:
        return None
