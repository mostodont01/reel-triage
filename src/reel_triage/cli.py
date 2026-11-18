"""reel-triage: sort saved Instagram reels with Claude.

    reel-triage add <link|id>...        queue reels
    reel-triage import <file>           queue everything from an Instagram export / text file
    reel-triage sort [-n N]             quick sort from captions (~50 per Claude call)
    reel-triage fetch [-n N] [ids]      download + frames + transcript (default: reels sorted "deep")
    reel-triage review [-n N] [ids]     Claude's deep verdicts (claude -p, checks the web)
    reel-triage run [-n N]              fetch + review whatever is pending
    reel-triage status                  counts
    reel-triage list [--verdict V] [--pick P]
    reel-triage show <id>               everything known about a reel (for a Claude session)
    reel-triage verdict <id> <file|->   store a verdict written by hand
    reel-triage pick <id> <want|tried|dismissed|none>
    reel-triage app                     the desktop app (install-desktop adds it to the menu)
    reel-triage serve                   the feed page
    reel-triage install-skill           link the /reels skill into ~/.claude/skills
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from . import ids, importer
from .store import PICKS, Store


def _codes(args_ids: list[str]) -> list[str]:
    out = []
    for raw in args_ids:
        code = ids.parse(raw)
        if not code:
            sys.exit(f"not an Instagram link or post id: {raw}")
        out.append(code)
    return out


def cmd_add(store: Store, a) -> None:
    new = sum(store.add(c, "manual") for c in _codes(a.ids))
    print(f"queued {new} new, {len(a.ids) - new} already known")


def cmd_import(store: Store, a) -> None:
    found = importer.read(Path(a.file))
    new = sum(store.add(code, f"import:{Path(a.file).name}", **info) for code, info in found.items())
    print(f"found {len(found)} posts: {new} new, {len(found) - new} already known")


def _select(store: Store, a, pending: list[dict]) -> list[str]:
    codes = _codes(a.ids) if a.ids else [m["id"] for m in pending]
    for c in codes:
        if not store.exists(c):
            store.add(c, "manual")
    return codes[: a.limit] if a.limit else codes


def _stop(usage: dict, a) -> bool:
    from . import claude

    reason = claude.over(usage, a.max_5h, a.max_week)
    if reason:
        print(f"stopping: {reason} (limits: --max-5h {a.max_5h}, --max-week {a.max_week})")
    return bool(reason)


def cmd_sort(store: Store, a) -> None:
    from . import claude, sort

    todo = sort.unsorted(store)
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} reels to sort, {a.batch} per call")
    for i in range(0, len(todo), a.batch):
        batch = todo[i: i + a.batch]
        t = time.time()
        try:
            done, usage = sort.sort_batch(store, batch, model=a.model or None)
        except claude.UsageLimit as e:
            print(f"usage limit: {e}")
            return
        except claude.ClaudeError as e:
            print(f"  batch failed, skipping it: {e}")
            continue
        left = len(todo) - i - len(batch)
        use = ", ".join(f"{k} {v:.0%}" for k, v in usage.items())
        print(f"  sorted {done}/{len(batch)} in {time.time() - t:.0f} s, {left} left  [{use}]")
        if _stop(usage, a):
            return


def cmd_fetch(store: Store, a) -> list[str]:
    from . import fetch

    codes = _select(store, a, store.to_fetch(everything=a.all))
    done = []
    for i, code in enumerate(codes, 1):
        print(f"[{i}/{len(codes)}] fetch {code}")
        t = time.time()
        meta = fetch.fetch(store, code, model=a.whisper, cookies_from=a.cookies)
        if meta["status"] == "fetched":
            done.append(code)
            print(f"  ok ({meta.get('kind')}, {time.time() - t:.0f} s) {meta.get('author', '')}")
        if i < len(codes):
            time.sleep(a.pause)  # human pace towards Instagram
    return done


def cmd_review(store: Store, a) -> None:
    from . import review

    from . import claude

    codes = _select(store, a, store.to_review())
    failed = 0
    for i, code in enumerate(codes, 1):
        if store.get(code)["status"] != "fetched":
            print(f"[{i}/{len(codes)}] {code}: not fetched, skipping")
            continue
        print(f"[{i}/{len(codes)}] review {code}")
        try:
            v, usage = review.review(store, code, model=a.model or None)
        except claude.UsageLimit as e:
            print(f"usage limit: {e}")
            break
        except review.ReviewError as e:
            failed += 1
            print(f"  failed: {e}")
            continue
        use = ", ".join(f"{k} {x:.0%}" for k, x in usage.items())
        print(f"  {v['verdict'].upper():5} {'★' * v['quality']:5} [{v['category']}] {v['title']}  [{use}]")
        if _stop(usage, a):
            break
    if failed:
        print(f"{failed} reviews failed; run again to retry them")


def cmd_run(store: Store, a) -> None:
    cmd_fetch(store, a)
    cmd_review(store, a)


def cmd_status(store: Store, a) -> None:
    metas = store.all()
    status = Counter(m["status"] for m in metas)
    verdicts = Counter((store.verdict(m["id"]) or {}).get("verdict", "-") for m in metas)
    quick = Counter((m.get("quick") or {}).get("verdict", "-") for m in metas)
    picks = Counter(m.get("pick") or "-" for m in metas)
    print(f"{len(metas)} reels in {store.root}")
    print("  download: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    print("  quick:    " + ", ".join(f"{k} {v}" for k, v in sorted(quick.items())))
    print("  verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(verdicts.items())))
    print("  picks:    " + ", ".join(f"{k} {v}" for k, v in sorted(picks.items())))


def cmd_list(store: Store, a) -> None:
    for m in store.all():
        v = store.verdict(m["id"]) or {}
        if a.verdict and v.get("verdict") != a.verdict:
            continue
        if a.pick and (m.get("pick") or "none") != a.pick:
            continue
        if a.json:
            print(json.dumps({"id": m["id"], "url": m["url"], "pick": m.get("pick"), "verdict": v or None},
                             ensure_ascii=False))
            continue
        q = m.get("quick") or {}
        title = v.get("title") or q.get("title") or (m.get("caption") or "").split("\n")[0][:70]
        label = v.get("verdict") or (f"q:{q['verdict']}" if q else m["status"])
        print(f"{m['id']:14} {label[:7]:7} {'★' * v.get('quality', 0):5} "
              f"{(m.get('pick') or ''):9} {v.get('category') or q.get('category', ''):15} {title}")


def cmd_show(store: Store, a) -> None:
    from . import review

    code = _codes([a.id])[0]
    if not store.exists(code):
        sys.exit(f"unknown reel {code}")
    print(review.bundle(store, code))
    v = store.verdict(code)
    m = store.get(code)
    print(f"\nPick: {m.get('pick') or 'none'}")
    if v:
        print("\nVerdict:\n" + json.dumps(v, indent=2, ensure_ascii=False))


def cmd_verdict(store: Store, a) -> None:
    from . import review

    code = _codes([a.id])[0]
    if not store.exists(code):
        sys.exit(f"unknown reel {code}")
    text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    try:
        v = review.validate(json.loads(text))
    except (json.JSONDecodeError, review.ReviewError) as e:
        sys.exit(f"bad verdict: {e}")
    v.setdefault("model", "manual")
    v.setdefault("reviewed", time.strftime("%Y-%m-%dT%H:%M:%S"))
    store.set_verdict(code, v)
    print(f"saved verdict for {code}: {v['verdict']}")


def cmd_pick(store: Store, a) -> None:
    code = _codes([a.id])[0]
    store.set_pick(code, None if a.pick == "none" else a.pick)
    print(f"{code}: {a.pick}")


def cmd_serve(store: Store, a) -> None:
    from . import server

    server.serve(store, a.host, a.port or server.DEFAULT_PORT, open_browser=not a.no_open)


def cmd_app(store: Store, a) -> None:
    from .app import main as app_main

    sys.exit(app_main([sys.argv[0]], store))


def cmd_install_desktop(store: Store, a) -> None:
    from .app import desktop

    if a.uninstall:
        desktop.uninstall()
        print("removed Reel Triage from the app menu")
    else:
        print(f"added Reel Triage to the app menu: {desktop.install()}")


def cmd_install_skill(store: Store, a) -> None:
    src = Path(__file__).resolve().parents[2] / "skill" / "reels"
    dest = Path.home() / ".claude" / "skills" / "reels"
    if not src.is_dir():
        sys.exit(f"skill folder not found: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.exists():
        if dest.is_symlink() and dest.resolve() == src:
            print(f"already installed: {dest}")
            return
        sys.exit(f"{dest} exists; remove it first")
    dest.symlink_to(src)
    print(f"linked {dest} -> {src}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reel-triage", description="Sort saved Instagram reels with Claude.")
    p.add_argument("--home", help="data directory (default ~/.local/share/reel-triage)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add", help="queue reels by link or id")
    s.add_argument("ids", nargs="+")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("import", help="queue everything from an Instagram export (zip/folder/json) or a text file")
    s.add_argument("file")
    s.set_defaults(func=cmd_import)

    def work_opts(s, fetch=True, review=True):
        s.add_argument("ids", nargs="*", help="specific reels (default: all pending)")
        s.add_argument("-n", "--limit", type=int, default=0, help="at most N reels")
        if fetch:
            s.add_argument("--all", action="store_true", help="every queued reel, not only those sorted 'deep'")
            s.add_argument("--whisper", default="small", help="Whisper model (tiny/base/small/medium)")
            s.add_argument("--cookies", metavar="BROWSER", help="use this browser's Instagram login, e.g. firefox")
            s.add_argument("--pause", type=float, default=3.0, help="seconds between downloads")
        if review:
            limits(s)

    def limits(s):
        s.add_argument("--model", default="sonnet", help="Claude model ('' = your default)")
        s.add_argument("--max-5h", type=float, default=0.8, help="stop when the 5-hour window is this full")
        s.add_argument("--max-week", type=float, default=0.9, help="stop when the weekly window is this full")

    s = sub.add_parser("sort", help="quick sort from captions")
    s.add_argument("-n", "--limit", type=int, default=0, help="at most N reels")
    s.add_argument("--batch", type=int, default=50, help="reels per Claude call")
    limits(s)
    s.set_defaults(func=cmd_sort)

    s = sub.add_parser("fetch", help="download, frames, transcript")
    work_opts(s, review=False)
    s.set_defaults(func=cmd_fetch)
    s = sub.add_parser("review", help="Claude's verdicts for fetched reels")
    work_opts(s, fetch=False)
    s.set_defaults(func=cmd_review)
    s = sub.add_parser("run", help="fetch + review")
    work_opts(s)
    s.set_defaults(func=cmd_run)

    sub.add_parser("status").set_defaults(func=cmd_status)

    s = sub.add_parser("list")
    s.add_argument("--verdict", choices=["try", "keep", "maybe", "skip"])
    s.add_argument("--pick", choices=[*PICKS, "none"])
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("show")
    s.add_argument("id")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("verdict", help="store a verdict written by hand (JSON)")
    s.add_argument("id")
    s.add_argument("file", help="JSON file or - for stdin")
    s.set_defaults(func=cmd_verdict)

    s = sub.add_parser("pick")
    s.add_argument("id")
    s.add_argument("pick", choices=[*PICKS, "none"])
    s.set_defaults(func=cmd_pick)

    s = sub.add_parser("serve", help="open the feed")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=None, help="default 8790; the next free port if busy")
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(func=cmd_serve)

    sub.add_parser("app", help="open the desktop app").set_defaults(func=cmd_app)
    s = sub.add_parser("install-desktop", help="add the app to the app menu")
    s.add_argument("--uninstall", action="store_true")
    s.set_defaults(func=cmd_install_desktop)

    sub.add_parser("install-skill", help="link the /reels skill into ~/.claude/skills").set_defaults(func=cmd_install_skill)
    return p


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(line_buffering=True)  # progress shows up in log files
    a = parser().parse_args(argv)
    store = Store(Path(a.home) if a.home else None)
    a.func(store, a)
