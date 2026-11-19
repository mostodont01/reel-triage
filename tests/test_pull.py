import json

import pytest

from reel_triage import cli, fetch, pull


def test_prompt_and_command(store, tmp_path):
    store.add("AAAAAA", saved_at=100)
    store.add("BBBBBB", saved_at=200)
    p = pull.prompt(store, "@someone ")
    assert "https://www.instagram.com/someone/saved/all-posts/" in p
    assert "BBBBBB AAAAAA" in p  # newest first
    cmd = pull.command(tmp_path / "mcp.json", "sonnet")
    assert cmd[cmd.index("--tools") + 1] == ""  # no built-in tools
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--mcp-config") + 1] == str(tmp_path / "mcp.json")
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__borrowed-hands__*"


def test_add_found_keeps_page_order(store):
    store.add("AAAAAA")
    new = pull.add_found(store, ["CCCCCC", "https://www.instagram.com/reel/DDDDDD/", "AAAAAA", "CCCCCC", "bad id!"])
    assert new == ["CCCCCC", "DDDDDD"]
    assert store.get("CCCCCC")["saved_at"] > store.get("DDDDDD")["saved_at"]
    assert store.get("CCCCCC")["source"] == "pull"


def test_fill_captions(store, monkeypatch):
    store.add("CCCCCC")
    store.add("DDDDDD")
    infos = {"CCCCCC": {"description": "you need this plugin", "uploader": "Ann"}}

    def peek(code, cookies_from=None):
        if code not in infos:
            raise fetch.FetchError("login required")
        return infos[code]

    monkeypatch.setattr(fetch, "peek", peek)
    pull.fill_captions(store, ["CCCCCC", "DDDDDD"], log=lambda *_: None)
    assert store.get("CCCCCC")["caption"] == "you need this plugin" and store.get("CCCCCC")["author"] == "Ann"
    assert store.get("DDDDDD")["source"] == "manual"  # no caption: straight to a full review


def test_cmd_pull(store, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        cli.main(["pull"])  # no username known yet
    seen = {}

    def fake_ask(st, user, model=None):
        seen["user"] = user
        return {"codes": ["EEEEEE"], "reached_known": True, "note": "2 new"}, {"five_hour": 0.3, "seven_day": 0.5}

    monkeypatch.setattr(pull, "ask_claude", fake_ask)
    monkeypatch.setattr(pull, "fill_captions", lambda *a, **k: None)
    cli.main(["pull", "--user", "@someone"])
    out = capsys.readouterr().out
    assert seen["user"] == "someone" and "1 new" in out and "[five_hour 30%, seven_day 50%]" in out
    assert store.settings()["instagram_user"] == "someone"
    cli.main(["pull"])  # remembered
    assert "0 new" in capsys.readouterr().out


def test_ask_claude_needs_hands(store, monkeypatch, tmp_path):
    monkeypatch.setenv("REEL_TRIAGE_HANDS", "")
    monkeypatch.setattr(pull, "HANDS_CANDIDATES", ())
    monkeypatch.setattr(pull.shutil, "which", lambda name: None)
    with pytest.raises(pull.claude.ClaudeError, match="Borrowed Hands"):
        pull.ask_claude(store, "someone")


def test_mcp_config_has_only_hands(store, monkeypatch, tmp_path):
    monkeypatch.setenv("REEL_TRIAGE_HANDS", "/opt/hands")
    monkeypatch.setattr(pull.claude, "find_claude", lambda: "/bin/claude")
    captured = {}

    def fake_run(cmd, **kw):
        config = cmd[cmd.index("--mcp-config") + 1]
        captured["config"] = json.loads(open(config).read())

        class P:
            returncode, stderr = 0, ""
            stdout = json.dumps({"type": "result", "subtype": "success", "structured_output": {"codes": [], "reached_known": True, "note": ""}})
        return P()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    data, _ = pull.ask_claude(store, "someone")
    assert captured["config"] == {"mcpServers": {"borrowed-hands": {"command": "/opt/hands", "args": ["mcp"]}}}
    assert data["codes"] == []
