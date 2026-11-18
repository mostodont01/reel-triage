---
name: reels
description: Go through the user's saved Instagram reels with reel-triage - pull in newly saved ones, quick-sort and deep-review them, open the feed, and implement the tools the user picked ("Implement" in the feed). Use when the user says /reels, "check my reels", "go through my saved reels", or asks to implement something they picked in the feed.
---

# Saved reels

`reel-triage` (repo `~/Programming/reel-triage`, installed with
`uv tool install -e`) keeps every saved reel in `~/.local/share/reel-triage`:
caption, author, collections, a quick sort from the caption, and for the
promising ones a deep review (video, transcript, frames, web-checked verdict).
`~/.local/share/reel-triage/context.md` describes the user's setup for the
reviewer; update it when their setup changes (new MCP server, plugin, project).

## 1. Where things stand
Run `reel-triage status`. Tell the user in one or two lines.

## 2. Pull in new reels
New reels sit at the top of the user's Saved page. Pick whichever fits:
- The user pasted links or has a new Instagram export zip:
  `reel-triage add <links>` / `reel-triage import <zip>`.
- Otherwise use Borrowed Hands: `open_browser("https://www.instagram.com/")`,
  `import_login("instagram.com")` if not logged in, `navigate` to
  `https://www.instagram.com/<username>/saved/all-posts/`, `read_page(full=True)`
  and collect the `/p/<id>/` links. Only the first screens matter (the grid
  only keeps visible rows; stop when the links are all known). Then
  `reel-triage add <ids>` and `close_browser()`.
Never scrape Instagram with automated logins.

## 3. Sort and review
- `reel-triage sort` - quick sort of everything unsorted (~50 per call, cheap).
- `reel-triage run -n 20` - fetch + deep review of reels sorted "deep" (and ones
  added by hand), newest first. ~45 s and one Claude call each. Both stop on
  their own when the 5-hour window is 80% full or the week 90%
  (`--max-5h`, `--max-week`). For big batches run in the background and tell the
  user how many are left.
- A single reel by hand: `reel-triage show <id>` prints everything; read the
  frames, check the web, then `reel-triage verdict <id> -` with the JSON
  (fields: category, title, summary, comment, verdict try|keep|maybe|skip,
  quality 1-5, optional action, tool{name,url,stars,last_update,already_have,
  built_in,safety}, projects, links).

## 4. The feed
`reel-triage serve` (run it in the background; it opens
http://127.0.0.1:8790). The user filters by verdict, category and status and
marks reels Implement / Tried / Dismiss.

## 5. Implement what they picked
`reel-triage list --pick want --json`, then for each:
1. Re-check before touching anything: open the repo, read the README and the
   install script / plugin / skill files. Check it isn't already installed or
   built in (`claude mcp list` names only - never open MCP config files: they
   hold Onshape API keys). Say what it will do and what it can access.
2. Ask the user before installing (plugins, skills and MCP servers run code).
   Root actions use `pkexec` and always need a yes.
3. Install it, try it on something real from their projects, report.
4. `reel-triage pick <id> tried` (or `dismissed` if it turned out bad, with a
   note to the user why). Update `context.md` so the reviewer knows they have it.
