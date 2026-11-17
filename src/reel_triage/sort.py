"""Quick sort: triage many reels from their caption alone (no download),
~50 per `claude -p` call. Decides which ones deserve a deep review.

Stored in meta.json as "quick": {category, verdict, title, note} with
verdict deep | keep | skip.
"""

import datetime as dt
import json

from . import claude
from .review import CATEGORIES
from .store import Store

QUICK = ["deep", "keep", "skip"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "category", "verdict", "title", "note"],
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "verdict": {"type": "string", "enum": QUICK},
                    "title": {"type": "string", "description": "What it is, max ~60 chars"},
                    "note": {"type": "string", "description": "One short sentence: why"},
                },
            },
        }
    },
}

SYSTEM_PROMPT = """\
You pre-sort a person's saved Instagram reels from their captions only (no
video). For EVERY reel in the list return: category, a short title, a
one-sentence note, and a verdict:

  deep = worth a full review (video, transcript, web checks): a concrete
         tool, repo, app, plugin, product, technique or project idea that
         could plausibly help THIS person (see their setup and projects),
         or a claim that needs checking before acting on it.
  keep = worth keeping but needs no review: funny, inspiring, personal
         interest, reference (music, psychology, motivation, food...).
  skip = nothing worth keeping: empty or spammy clickbait, outdated tech,
         "comment X" bait with no named thing, a duplicate.

The person saved every one of these on purpose. Personal-taste content
(memes, motivation, psychology, music, sport) is keep, not skip, unless it
is empty or spam; skip is mainly for tech/tool reels that are outdated,
hype or have nothing concrete. No caption: judge by the author name if it
clearly says what the account is about (a tech account: deep), otherwise
keep with the note "no caption". Be decisive. Old AI/tool reels (2023-2024)
are often outdated: deep only if the thing is likely still relevant. The
person's own collection names are a hint of what they cared about. Captions
may be Czech; notes and titles in English. Return the ids exactly as given."""


def _entry(m: dict) -> dict:
    saved = dt.date.fromtimestamp(m["saved_at"]).isoformat() if m.get("saved_at") else None
    caption = (m.get("caption") or "").strip()
    if len(caption) > 700:
        caption = caption[:700] + "…"
    entry = {"id": m["id"], "author": m.get("author_id") or m.get("author"), "saved": saved,
             "caption": caption}
    if m.get("collections"):
        entry["collections"] = m["collections"]
    return entry


def prompt(store: Store, metas: list[dict]) -> str:
    context = store.context().strip() or "(no information about the person)"
    return (
        f"Today is {dt.date.today().isoformat()}.\n\n"
        f"## The person and their setup\n{context}\n\n"
        f"## Reels ({len(metas)})\n"
        + "\n".join(json.dumps(_entry(m), ensure_ascii=False) for m in metas)
    )


def apply(store: Store, metas: list[dict], data: dict) -> int:
    """Store results; returns how many reels got one. Unknown ids and invalid
    rows are ignored (those reels stay unsorted and come again next run)."""
    wanted = {m["id"] for m in metas}
    done = 0
    for item in data.get("items") or []:
        if not isinstance(item, dict) or item.get("id") not in wanted:
            continue
        if item.get("category") not in CATEGORIES or item.get("verdict") not in QUICK:
            continue
        store.update(item["id"], quick={
            "category": item["category"], "verdict": item["verdict"],
            "title": str(item.get("title", ""))[:120], "note": str(item.get("note", ""))[:400],
        })
        wanted.discard(item["id"])
        done += 1
    return done


def unsorted(store: Store) -> list[dict]:
    return [m for m in store.all() if not m.get("quick") and not store.verdict(m["id"])]


def sort_batch(store: Store, metas: list[dict], model: str | None = "sonnet") -> tuple[int, dict]:
    data, usage = claude.run(prompt(store, metas), SCHEMA, SYSTEM_PROMPT, model=model, timeout=900)
    return apply(store, metas, data), usage
