# reel-triage

Sort your saved Instagram reels with Claude. Built for the pile of "you NEED
this Claude plugin" reels (and everything else you ever saved): which ones
are real, current and worth trying, and which are hype, outdated or already
built in.

1. **Import** your saved posts from Instagram's data export (captions, authors,
   your collections, when you saved them) or paste links.
2. **Quick sort** everything from the captions alone, ~50 reels per Claude call:
   category plus *deep look* / *keep* / *skip*.
3. **Deep review** the promising ones: download the reel, pull frames (on-screen
   text often names the tool), transcribe the audio locally with Whisper, and
   let Claude verify the tool on the web (repo, stars, last update, install
   risks, already built in or already in your setup).
4. **Browse** in the desktop app (or the web feed): the reel plays next to
   Claude's comment, with filters, and you mark reels *Implement* / *Tried* /
   *Dismiss*.
5. **Implement** the picked ones in a Claude Code session (`/reels` skill).

Claude runs through the Claude Code CLI (`claude -p`) on your existing login,
so no API key is needed. Batch commands stop on their own before your plan's
5-hour or weekly window fills up.

## Install

```bash
git clone https://github.com/mostodont01/reel-triage
cd reel-triage
uv tool install -e .          # puts `reel-triage` on your PATH
reel-triage install-desktop   # the app in your app menu (Reel Triage)
reel-triage install-skill     # optional: the /reels skill for Claude Code
```

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and
[Claude Code](https://claude.com/claude-code) (logged in). ffmpeg comes as a
pip wheel, so no system packages or root are needed.

## The app

`reel-triage app` (or *Reel Triage* in the app menu) is a PySide6 + QML
desktop app: filters by verdict, your picks and category on the left, the
reels in the middle, the selected reel on the right (video, the frames
Claude saw, its verdict, the tool it checked, the install command with a Copy
button). **Get new reels…** can **ask Claude to pull your new saves**: it
reads your Instagram Saved page in a [Borrowed Hands](https://github.com/mostodont01/borrowed-hands)
window (a real browser you can see and help in; Claude only gets that one
tool), then sorts and reviews what's new. It also takes pasted links or an
export zip; **Sort &
review** runs `sort` and `run` with a live log and stops on its own at 80 %
of the 5-hour window; the Claude usage bars sit at the bottom left.
Keys: ↑ ↓ move, I implement, T tried, D dismiss, Ctrl+F search.

## Use

```bash
# Instagram: Settings → Accounts Center → Your information and permissions →
# Export your information → Saved, JSON, all time. Then:
reel-triage import ~/Downloads/instagram-yourname-….zip
reel-triage add https://www.instagram.com/reel/…   # or single links
reel-triage pull --user yourname                   # or let Claude read your new saves (Borrowed Hands)

reel-triage sort          # quick sort from captions
reel-triage run -n 20     # deep review of the 20 newest "deep look" reels
reel-triage app           # the desktop app
reel-triage serve         # or the web feed at http://127.0.0.1:8790
reel-triage status
```

Tell the reviewer about yourself in `~/.local/share/reel-triage/context.md`
(your setup, tools you already have, your projects): that's what makes the
verdicts personal ("you already have this", "useful for your robot").

Other commands: `fetch`, `review`, `list [--verdict try] [--pick want]`,
`show <id>`, `verdict <id> <file|->`, `pick <id> <want|tried|dismissed|none>`.
`reel-triage <command> --help` for options (Whisper model, Claude model,
usage limits, `--cookies firefox` for reels that need a login).

## Data and privacy

Everything stays on your machine in `~/.local/share/reel-triage`
(`REEL_TRIAGE_HOME` overrides it): one folder per reel with `meta.json`,
`verdict.json`, the video, frames and transcript. Share-link tracking
parameters are dropped. Downloads go at a human pace (`--pause`) and without
a login unless you pass `--cookies`.

## Development

```bash
uv sync
uv run pytest
```

Layout: `ids` (links), `importer` (exports), `store` (data folder), `fetch`
(yt-dlp, ffmpeg, faster-whisper), `claude` (`claude -p` + usage), `sort`
(quick sort), `review` (deep review), `server` + `feed.html` (the feed),
`cli`.

MIT license.
