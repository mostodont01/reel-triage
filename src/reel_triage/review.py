"""Claude's deep review of a fetched reel (`claude -p`, see claude.py). The reviewer may read the frames and check
claims on the web (GitHub stars, last commit, whether it is built in already).
"""

import datetime as dt

from . import claude
from .store import Store

CATEGORIES = [
    "claude-tool",     # Claude skills, plugins, MCP servers, Claude Code tips
    "ai-tool",         # other AI apps, models, local LLM tools
    "dev-tool",        # programming tools, libraries, apps, Linux tricks
    "electronics",
    "3d-printing",
    "cad-engineering",
    "robotics",
    "maker-project",   # DIY build ideas
    "learning",        # science, explanations, tutorials
    "music",
    "health-fitness",
    "food",
    "humor",
    "lifestyle",
    "other",
]
VERDICTS = ["try", "keep", "maybe", "skip"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["category", "title", "summary", "comment", "verdict", "quality"],
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "title": {"type": "string", "description": "Short name of the thing, max ~60 chars"},
        "summary": {"type": "string", "description": "What the reel says / shows, 1-2 sentences"},
        "comment": {"type": "string", "description": "Your honest take, to the user, 2-5 sentences"},
        "verdict": {"type": "string", "enum": VERDICTS},
        "quality": {"type": "integer", "minimum": 1, "maximum": 5},
        "action": {"type": "string", "description": "Concrete next step, e.g. the install command; empty if none"},
        "tool": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "url": {"type": "string"},
                "stars": {"type": "string", "description": "e.g. '39k', as checked"},
                "last_update": {"type": "string", "description": "e.g. '2026-11 (active)'"},
                "already_have": {"type": "boolean"},
                "built_in": {"type": "boolean", "description": "Claude Code / the OS already does this"},
                "safety": {"type": "string", "description": "Install-risk notes; empty if nothing notable"},
            },
        },
        "projects": {"type": "array", "items": {"type": "string"},
                     "description": "The user's projects this helps, by name"},
        "links": {"type": "array", "items": {"type": "string"}},
    },
}

SYSTEM_PROMPT = """\
You sort a person's saved Instagram reels. For each reel you get its caption,
an automatic transcript and paths of a few video frames. Look at the frames
with the Read tool: on-screen text often names the tool, repo or command.

Decide:
- category (fixed list),
- verdict:
  try   = worth acting on: install/try the tool, build the project, check the
          product, learn the thing. Only when it is real, current and useful
          for THIS person.
  keep  = worth keeping, nothing to do (funny, inspiring, good reference).
  maybe = could be useful later / with caveats.
  skip  = hype, outdated, already built in, already installed, dead or sketchy
          repo, clickbait with no substance, or irrelevant to them.
- quality 1-5: how solid and useful the reel's information is (1 = clickbait
  or wrong, 5 = accurate and genuinely useful).

Tools, repos, apps, products: VERIFY before judging. Use WebSearch/WebFetch to
find the real project (GitHub repo, official page): stars, last commit or
release, what it actually does, and whether Claude Code or the person's
existing setup (listed below) already covers it. Many "you NEED this Claude
plugin" reels show something that is now built in, renamed or abandoned; say
so. Flag install risks (curl | bash from unknown sources, closed-source
binaries, wants API keys or broad permissions). Put the real link in
tool.url and the install command, if any, in action. "Comment X for the link"
reels: find the link yourself. Never invent stars, dates or links; if you
could not check something, say so.

Not a tool (humor, food, music, learning...): no web checks needed unless the
reel makes a factual claim worth checking. Judge it for this person.

comment: 2-5 plain sentences written to the person ("you"), honest and
specific: is it worth their time and why, how it fits what they already do.
No hype, no emoji. Write in English."""


class ReviewError(Exception):
    pass


def bundle(store: Store, code: str) -> str:
    """Everything known about a reel, as text (for the reviewer or for a
    Claude session doing the review by hand)."""
    m = store.get(code)
    folder = store.path(code)
    transcript = (folder / "transcript.txt")
    transcript = transcript.read_text(encoding="utf-8").strip() if transcript.is_file() else ""
    lines = [
        f"Reel {code}: {m['url']}",
        f"Author: {m.get('author') or '?'}    Posted: {m.get('posted') or '?'}    "
        f"Likes: {m.get('likes') if m.get('likes') is not None else '?'}    "
        f"Kind: {m.get('kind') or '?'}    Duration: {m.get('duration') or '?'} s",
        f"Hashtags: {' '.join('#' + h for h in m.get('hashtags') or []) or '-'}",
        f"In the person's own collections: {', '.join(m.get('collections') or []) or '-'}",
        "",
        "Caption:",
        m.get("caption") or "(none)",
        "",
        f"Transcript ({m.get('language') or 'no speech'}):",
        transcript or "(no speech)",
        "",
        "Frames (read them for on-screen text):",
    ]
    lines += [f"  {folder / f}" for f in m.get("frames") or []] or ["  (none)"]
    return "\n".join(lines)


def prompt(store: Store, code: str) -> str:
    context = store.context().strip() or "(no information about the person's setup)"
    return (
        f"Today is {dt.date.today().isoformat()}.\n\n"
        f"## The person and their setup\n{context}\n\n"
        f"## The reel\n{bundle(store, code)}\n\n"
        "Review it and answer with the structured output."
    )


def validate(v: dict) -> dict:
    """Check a verdict (also used for verdicts written by hand)."""
    if not isinstance(v, dict):
        raise ReviewError("verdict must be a JSON object")
    missing = [k for k in SCHEMA["required"] if k not in v]
    if missing:
        raise ReviewError(f"verdict is missing: {', '.join(missing)}")
    unknown = set(v) - set(SCHEMA["properties"]) - {"reviewed", "model"}
    if unknown:
        raise ReviewError(f"unknown verdict fields: {', '.join(sorted(unknown))}")
    if v["category"] not in CATEGORIES:
        raise ReviewError(f"category must be one of {CATEGORIES}")
    if v["verdict"] not in VERDICTS:
        raise ReviewError(f"verdict must be one of {VERDICTS}")
    if not isinstance(v["quality"], int) or not 1 <= v["quality"] <= 5:
        raise ReviewError("quality must be an integer 1-5")
    if "tool" in v and v["tool"] is not None and not (isinstance(v["tool"], dict) and v["tool"].get("name")):
        raise ReviewError("tool needs at least a name")
    return v


def review(store: Store, code: str, model: str | None = "sonnet", timeout: float = 600) -> tuple[dict, dict]:
    """Review one fetched reel; returns (verdict, usage)."""
    try:
        data, usage = claude.run(prompt(store, code), SCHEMA, SYSTEM_PROMPT,
                                 tools="Read,WebSearch,WebFetch", model=model,
                                 cwd=store.path(code), timeout=timeout)
    except claude.UsageLimit:
        raise
    except claude.ClaudeError as e:
        raise ReviewError(str(e)) from None
    verdict = validate(data)
    verdict["reviewed"] = dt.datetime.now().isoformat(timespec="seconds")
    verdict["model"] = model or "default"
    store.set_verdict(code, verdict)
    return verdict, usage
