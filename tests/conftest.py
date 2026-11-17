import pytest

from reel_triage.store import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("REEL_TRIAGE_HOME", str(tmp_path / "data"))
    return Store(tmp_path / "data")


def verdict(**over):
    v = {
        "category": "claude-tool",
        "title": "Some plugin",
        "summary": "A reel about a plugin.",
        "comment": "Real and maintained, but you already have something similar.",
        "verdict": "maybe",
        "quality": 3,
    }
    v.update(over)
    return v
