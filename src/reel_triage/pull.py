"""Pull newly saved reels from Instagram: Claude reads the user's Saved page
through Borrowed Hands (a real browser window the user can see and help in),
so there are no automated logins and no scraping.

    reel-triage pull [--user NAME]

Only Borrowed Hands' tools are available to that Claude run: its own MCP
config with just that server (--strict-mcp-config), no built-in tools.
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import claude, ids
from .store import Store

SCHEMA = {
    "type": "object",
    "properties": {
        "codes": {"type": "array", "items": {"type": "string"},
                  "description": "post ids from the Saved grid, in page order (newest first)"},
        "reached_known": {"type": "boolean",
                          "description": "true if the page got as far as ids from the known list"},
        "note": {"type": "string", "description": "one line for the user: what happened, any problem"},
    },
    "required": ["codes", "reached_known", "note"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You collect the user's newest saved Instagram posts with Borrowed Hands: a
browser window on the user's screen. You read pages yourself; the user only
does what you can't (scrolling, logging in, captchas).

Steps:
1. open_browser(SAVED_URL), then read_page(full=True).
2. If it is a login page: import_login("instagram.com") (copies the login from
   the user's Firefox), navigate(SAVED_URL) and read again. If still logged out,
   instruct the user to log in in the window, wait, then navigate(SAVED_URL).
3. Collect every post link on the page: /p/<id>/, /reel/<id>/ or /tv/<id>/ (the
   id is the part after it), in page order. The newest saves are at the top.
4. Compare with the KNOWN ids (the newest saves already pulled). As soon as a
   few known ids show up, you have everything new: stop.
   If none show up yet, instruct the user: "Scroll down a little in the window,
   then click Done", wait, read_page(full=True) again and collect more. The
   grid only keeps the rows on screen, so collect after every scroll. At most
   8 rounds.
5. close_browser(), then answer.

Rules: never ask for passwords or payment details; stay on instagram.com; one
short, concrete instruction at a time. If the window is closed or the user
gives up (session_ended), answer with what you have.
"""

HANDS_CANDIDATES = (
    Path.home() / "Programming" / "human-robot-cli" / ".venv" / "bin" / "hands",
    Path.home() / ".local" / "bin" / "hands",
)


def find_hands() -> str | None:
    """The Borrowed Hands command (REEL_TRIAGE_HANDS overrides)."""
    env = os.environ.get("REEL_TRIAGE_HANDS")
    if env:
        return env
    found = shutil.which("hands")
    if found:
        return found
    return next((str(p) for p in HANDS_CANDIDATES if p.is_file() and os.access(p, os.X_OK)), None)


def saved_url(user: str) -> str:
    return f"https://www.instagram.com/{user.strip().lstrip('@')}/saved/all-posts/"


def known_recent(store: Store, n: int = 40) -> list[str]:
    return [m["id"] for m in store.all()[:n]]


def prompt(store: Store, user: str) -> str:
    return (f"SAVED_URL: {saved_url(user)}\n\n"
            f"KNOWN ids (newest first): {' '.join(known_recent(store))}\n\n"
            "Collect the ids of saves newer than these.")


def command(mcp_config: Path, model: str | None) -> list[str]:
    cmd = [
        claude.find_claude() or "claude", "-p",
        "--output-format", "stream-json", "--verbose",
        "--json-schema", json.dumps(SCHEMA),
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", str(mcp_config),
        "--allowedTools", "mcp__borrowed-hands__*",
        "--setting-sources", "",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    if model:
        cmd += ["--model", model]
    return cmd


def ask_claude(store: Store, user: str, model: str | None = "sonnet", timeout: float = 1200) -> tuple[dict, dict]:
    """Claude's answer (codes, reached_known, note) and the usage windows."""
    import subprocess

    hands = find_hands()
    if not hands:
        raise claude.ClaudeError("Borrowed Hands ('hands') was not found; set REEL_TRIAGE_HANDS")
    if claude.find_claude() is None:
        raise claude.ClaudeError("the 'claude' command was not found")
    with tempfile.TemporaryDirectory(prefix="reel-triage-pull-") as tmp:
        config = Path(tmp) / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {"borrowed-hands": {"command": hands, "args": ["mcp"]}}}))
        try:
            proc = subprocess.run(command(config, model), input=prompt(store, user), cwd=tmp,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise claude.ClaudeError(f"no answer within {timeout:.0f} s") from None
    return claude.parse_stream(proc.stdout, proc.returncode, proc.stderr)


def add_found(store: Store, codes: list[str]) -> list[str]:
    """Queue the new ones. They count as saved just now, in page order."""
    clean = [c for c in dict.fromkeys(ids.parse(c) or "" for c in codes) if c]
    now = int(time.time())
    new = []
    for i, code in enumerate(clean):
        if store.add(code, "pull", saved_at=now - i):
            new.append(code)
    return new


def fill_captions(store: Store, codes: list[str], cookies_from: str | None = None, log=print) -> None:
    """Caption and author from Instagram (no download) so the quick sort has
    something to go on. Reels without them get a full review instead."""
    from . import fetch

    for code in codes:
        try:
            info = fetch.describe(fetch.peek(code, cookies_from))
        except fetch.FetchError as e:
            log(f"  {code}: no caption ({str(e)[:80]}); it gets a full review")
            store.update(code, source="manual")
            continue
        store.update(code, **{k: info[k] for k in ("caption", "author", "author_id") if info.get(k)})
        if not info.get("caption"):
            store.update(code, source="manual")
        log(f"  {code}: {(info.get('author') or '?')} · {(info.get('caption') or '').splitlines()[0][:60] if info.get('caption') else 'no caption'}")
