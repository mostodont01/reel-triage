import json

import pytest

from reel_triage import claude, review, sort
from conftest import verdict


def stream(result: dict | None, rate=None) -> str:
    lines = [json.dumps({"type": "system"})]
    if rate:
        lines.append(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": rate}}))
    if result is not None:
        lines.append(json.dumps(result))
    return "\n".join(lines)


def test_parse_stream_structured_output_and_usage():
    out = stream({"type": "result", "subtype": "success", "structured_output": {"a": 1}},
                 {"five_hour": {"utilization": 0.42, "resetsAt": 1}, "seven_day": {"utilization": 0.1}})
    data, usage = claude.parse_stream(out)
    assert data == {"a": 1}
    assert usage == {"five_hour": 0.42, "seven_day": 0.1}


def test_parse_stream_text_fallback_and_errors():
    data, _ = claude.parse_stream(stream({"type": "result", "subtype": "success", "result": '{"b": 2}'}))
    assert data == {"b": 2}
    with pytest.raises(claude.ClaudeError):
        claude.parse_stream(stream(None), 1, "boom")
    with pytest.raises(claude.UsageLimit):
        claude.parse_stream(stream({"type": "result", "subtype": "success", "is_error": True,
                                    "result": "You've hit your usage limit · resets 3am"}))
    with pytest.raises(claude.ClaudeError):
        claude.parse_stream(stream({"type": "result", "subtype": "success", "result": "not json"}))


def test_over():
    assert claude.over({"five_hour": 0.85}, 0.8, 0.9) == "5-hour window at 85%"
    assert claude.over({"seven_day": 0.95}, 0.8, 0.9) == "weekly window at 95%"
    assert claude.over({}, 0.8, 0.9) is None


def test_command_is_lean():
    cmd = claude.command({"type": "object"}, "sys", tools="Read,WebFetch", model="sonnet")
    assert cmd[1] == "-p"
    assert cmd[cmd.index("--tools") + 1] == "Read,WebFetch"
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,WebFetch"
    assert "--strict-mcp-config" in cmd and "--no-session-persistence" in cmd
    assert "--allowedTools" not in claude.command({}, "sys")


def test_validate_verdict():
    assert review.validate(verdict())["verdict"] == "maybe"
    for bad in (verdict(verdict="yes"), verdict(category="cats"), verdict(quality=7),
                verdict(quality="3"), {"title": "x"}, verdict(extra=1), verdict(tool={"url": "x"})):
        with pytest.raises(review.ReviewError):
            review.validate(bad)
    assert review.validate(verdict(tool={"name": "x"}, reviewed="now", model="m"))


def test_bundle_and_prompt(store):
    store.add("AAAAAA", caption="Try this plugin", author="Bob", hashtags=["ai"], collections=["robotics"])
    store.update("AAAAAA", status="fetched", frames=["frames/01.jpg"], language="en")
    (store.path("AAAAAA") / "transcript.txt").write_text("hello there\n")
    store.context_file.write_text("Uses Claude Code.")
    b = review.bundle(store, "AAAAAA")
    assert "Try this plugin" in b and "hello there" in b and "#ai" in b and "robotics" in b
    assert str(store.path("AAAAAA") / "frames/01.jpg") in b
    assert "Uses Claude Code." in review.prompt(store, "AAAAAA")


def test_review_stores_verdict(store, monkeypatch):
    store.add("AAAAAA")
    store.update("AAAAAA", status="fetched")
    seen = {}

    def fake_run(prompt, schema, system, tools="", model=None, cwd=None, timeout=0):
        seen.update(tools=tools, cwd=cwd, model=model)
        return verdict(verdict="try"), {"five_hour": 0.1}

    monkeypatch.setattr(claude, "run", fake_run)
    v, usage = review.review(store, "AAAAAA")
    assert v["verdict"] == "try" and v["model"] == "sonnet" and "reviewed" in v
    assert store.verdict("AAAAAA")["verdict"] == "try"
    assert seen["cwd"] == store.path("AAAAAA") and "WebSearch" in seen["tools"]
    assert usage == {"five_hour": 0.1}


def test_review_bad_output_raises(store, monkeypatch):
    store.add("AAAAAA")
    monkeypatch.setattr(claude, "run", lambda *a, **k: ({"verdict": "nope"}, {}))
    with pytest.raises(review.ReviewError):
        review.review(store, "AAAAAA")
    assert store.verdict("AAAAAA") is None


def test_sort_prompt_and_apply(store):
    store.add("AAAAAA", caption="x" * 2000, author_id="bob", saved_at=1700000000, collections=["c"])
    store.add("BBBBBB", caption="meme")
    metas = sort.unsorted(store)
    p = sort.prompt(store, metas)
    lines = [json.loads(line) for line in p.splitlines() if line.startswith("{")]
    first = next(e for e in lines if e["id"] == "AAAAAA")
    assert first["author"] == "bob" and first["collections"] == ["c"] and len(first["caption"]) < 800
    data = {"items": [
        {"id": "AAAAAA", "category": "robotics", "verdict": "deep", "title": "t", "note": "n"},
        {"id": "BBBBBB", "category": "nonsense", "verdict": "keep", "title": "t", "note": "n"},
        {"id": "ZZZZZZ", "category": "humor", "verdict": "keep", "title": "t", "note": "n"},
    ]}
    assert sort.apply(store, metas, data) == 1
    assert store.get("AAAAAA")["quick"]["verdict"] == "deep"
    assert [m["id"] for m in sort.unsorted(store)] == ["BBBBBB"]
