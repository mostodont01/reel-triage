from reel_triage import feed, usage


def reel(id, verdict=None, quick=None, **kw):
    r = {"id": id, "verdict": verdict, "quick": quick, "status": "new", "pick": None, "saved_at": 0}
    r.update(kw)
    return r


REELS = [
    reel("A", verdict={"verdict": "try", "quality": 3, "category": "claude-tool", "title": "Ponytail"}, saved_at=1),
    reel("B", verdict={"verdict": "try", "quality": 5, "category": "electronics", "title": "GPIO"}, saved_at=2),
    reel("C", quick={"verdict": "deep", "category": "dev-tool", "title": "Byobu"}, saved_at=5),
    reel("D", quick={"verdict": "skip", "category": "humor", "title": "Meme"}, saved_at=9, pick="dismissed"),
    reel("E", status="failed", caption="first line\nsecond", saved_at=3),
    reel("F", verdict={"verdict": "skip", "quality": 1, "category": "humor", "title": "Hype"}, saved_at=8),
]


def test_vkey_and_title():
    assert [feed.vkey(r) for r in REELS] == ["try", "try", "check", "skip", "fail", "skip"]
    assert feed.title(REELS[4]) == "first line" and feed.title(REELS[2]) == "Byobu"
    assert feed.category(REELS[2]) == "dev-tool" and feed.category(REELS[4]) == ""


def test_filters():
    ids = lambda **kw: [r["id"] for r in REELS if feed.matches(r, **kw)]
    assert ids(verdict="try") == ["A", "B"]
    assert ids(verdict="check") == ["C", "E"]  # to check includes failed / unsorted
    assert ids(cat="humor") == ["D", "F"]
    assert ids(pick="dismissed") == ["D"] and "D" not in ids(pick="none")
    assert ids(query="gpio") == ["B"]


def test_order_and_counts():
    assert [r["id"] for r in feed.ordered(REELS)] == ["B", "A", "C", "E", "F", "D"]  # skips last
    assert [r["id"] for r in feed.ordered(REELS, "new")] == ["D", "F", "C", "E", "B", "A"]
    c = feed.counts(REELS)
    assert (c[""], c["try"], c["check"], c["skip"], c["pick:dismissed"], c["pick:none"]) == (6, 2, 2, 2, 1, 5)
    assert feed.categories(REELS)[0] == ("humor", 2)


def test_frame_time():
    assert feed.frame_time("frames/02_012.3s.jpg") == 12.3
    assert feed.frame_time("frames/01_image.jpg") is None


def test_usage_merge(tmp_path):
    f = tmp_path / "snap.json"
    f.write_text('{"five_hour": {"used_percentage": 20, "resets_at": 2000}, "seven_day": {"used_percentage": 40, "resets_at": 9000}}')
    snap = usage.load_statusbar(f)
    assert snap["five_hour"] == {"used": 0.2, "resets_at": 2000.0}
    live = usage.from_log_line("  TRY ★★★ [x] y  [five_hour 53%, seven_day 50%]")
    assert live == {"five_hour": 0.53, "seven_day": 0.5}
    m = usage.merge(snap, live, live_at=1000, now=1500)
    assert m["five_hour"]["used"] == 0.53 and m["seven_day"]["used"] == 0.5  # live is fresher
    m = usage.merge(snap, None, 0, now=2500)  # the 5-hour window has reset
    assert m["five_hour"]["used"] == 0.0 and m["seven_day"]["used"] == 0.4
    assert usage.merge({}, None, 0)["five_hour"]["known"] is False
