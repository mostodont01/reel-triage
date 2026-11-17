import pytest

from reel_triage.store import Store


def test_add_get_and_order(store):
    assert store.add("AAAAAA", saved_at=100) is True
    assert store.add("BBBBBB", saved_at=200, caption="hi", author="Bob") is True
    assert store.add("AAAAAA") is False
    assert [m["id"] for m in store.all()] == ["BBBBBB", "AAAAAA"]
    m = store.get("BBBBBB")
    assert (m["status"], m["caption"], m["author"], m["pick"]) == ("new", "hi", "Bob", None)


def test_add_again_fills_missing_fields_and_merges_collections(store):
    store.add("AAAAAA", collections=["a"])
    store.add("AAAAAA", saved_at=5, caption="cap", collections=["b", "a"])
    m = store.get("AAAAAA")
    assert m["saved_at"] == 5 and m["caption"] == "cap"
    assert m["collections"] == ["a", "b"]
    store.add("AAAAAA", caption="other")
    assert store.get("AAAAAA")["caption"] == "cap"  # never overwritten


def test_unknown_fields_are_ignored(store):
    store.add("AAAAAA", status="fetched", verdict="try")
    assert store.get("AAAAAA")["status"] == "new"


def test_picks(store):
    store.add("AAAAAA")
    store.set_pick("AAAAAA", "want")
    assert store.get("AAAAAA")["pick"] == "want"
    store.set_pick("AAAAAA", None)
    assert store.get("AAAAAA")["pick"] is None
    with pytest.raises(ValueError):
        store.set_pick("AAAAAA", "maybe")


def test_queues(store):
    store.add("MANUAL", source="manual")
    store.add("DEEPPP", source="import:x")
    store.add("KEEPPP", source="import:x")
    store.add("UNSORT", source="import:x")
    store.add("DONEEE", source="manual")
    store.update("DEEPPP", quick={"verdict": "deep"})
    store.update("KEEPPP", quick={"verdict": "keep"})
    store.update("DONEEE", status="fetched")
    assert {m["id"] for m in store.to_fetch()} == {"MANUAL", "DEEPPP"}
    assert len(store.to_fetch(everything=True)) == 4
    assert [m["id"] for m in store.to_review()] == ["DONEEE"]
    store.set_verdict("DONEEE", {"verdict": "try"})
    assert store.to_review() == []


def test_root_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("REEL_TRIAGE_HOME", str(tmp_path / "x"))
    assert Store().root == tmp_path / "x"
    assert (tmp_path / "x" / "reels").is_dir()
