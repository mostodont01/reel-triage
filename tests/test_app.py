"""The desktop app, headless (QT_QPA_PLATFORM=offscreen)."""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtQuick")

from PySide6.QtCore import QObject  # noqa: E402

from conftest import verdict  # noqa: E402
from reel_triage.app import create_engine, desktop  # noqa: E402
from reel_triage.app.backend import Backend  # noqa: E402


@pytest.fixture
def filled(store):
    store.add("AAAAAA", caption="a plugin", author="Ann", saved_at=10)
    store.add("BBBBBB", caption="meme", saved_at=20)
    store.add("CCCCCC", caption="robot", saved_at=30)
    store.set_verdict("AAAAAA", verdict(verdict="try", title="Cool tool", action="pip install x",
                                        tool={"name": "x", "url": "javascript:alert(1)"}))
    store.update("BBBBBB", quick={"category": "humor", "verdict": "skip", "title": "Meme", "note": "n"})
    store.update("CCCCCC", quick={"category": "robotics", "verdict": "deep", "title": "Robot", "note": "n"})
    return store


@pytest.fixture
def backend(qapp, filled):
    b = Backend(filled)
    yield b
    b.shutdown()


def ids(b):
    return [r["id"] for r in b.reels.rows()]


def test_filters_and_selection(backend):
    assert ids(backend) == ["AAAAAA", "CCCCCC", "BBBBBB"]  # best first
    assert backend.counts["try"] == 1 and backend.pending == 1
    backend.setVerdictFilter("skip")
    assert ids(backend) == ["BBBBBB"] and backend.matchCount == 1
    backend.setVerdictFilter("")
    backend.setSortMode("new")
    assert ids(backend)[0] == "CCCCCC"
    backend.setSearch("cool")
    assert ids(backend) == ["AAAAAA"]
    backend.selectRow(0)
    cur = backend.current
    assert cur["title"] == "Cool tool" and cur["action"] == "pip install x"
    assert cur["tool"]["url"] == ""  # only http(s) links are shown
    assert backend.currentRow == 0


def test_pick_toggles_and_saves(backend, filled):
    backend.setPick("AAAAAA", "want")
    assert filled.get("AAAAAA")["pick"] == "want" and backend.counts["pick:want"] == 1
    backend.setPick("AAAAAA", "want")  # again: cleared
    assert filled.get("AAAAAA")["pick"] is None
    backend.setPick("AAAAAA", "bogus")
    assert filled.get("AAAAAA")["pick"] is None


def test_add_links_and_import(backend, tmp_path):
    msg = backend.addLinks("look https://www.instagram.com/reel/DDDDDD/?igsh=1 and AAAAAA no")
    assert msg.startswith("Added 1 new reel") and "DDDDDD" in ids(backend)
    assert backend.addLinks("nothing here") == "No Instagram links found."
    f = tmp_path / "links.txt"
    f.write_text("https://www.instagram.com/p/EEEEEE/")
    assert "1 new" in backend.importExport(f.as_uri())
    assert "Couldn't read" in backend.importExport(str(tmp_path / "missing.zip"))


def test_pipeline_runs_the_cli(qapp, qtbot, tmp_path):
    # An empty store, so neither step needs Claude or the network.
    from reel_triage.store import Store

    backend = Backend(Store(tmp_path / "empty"))
    backend.stopPipeline()  # nothing running: no-op
    with qtbot.waitSignal(backend.message, timeout=60000) as sig:
        backend.runPipeline()
        assert backend.busy
    assert not backend.busy and "finished" in sig.args[0]
    assert "$ reel-triage sort" in backend.log and "$ reel-triage run" in backend.log
    assert "0 reels to sort" in backend.log
    backend.shutdown()
    backend.deleteLater()
    qtbot.wait(50)


def test_qml_loads(backend, qtbot):
    warnings = []
    engine = create_engine(backend)
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    assert engine.rootObjects()
    win = engine.rootObjects()[0]
    backend.selectRow(0)
    qtbot.wait(100)
    title = win.findChild(QObject, "detailTitle")
    assert title.property("text") == "Cool tool"
    assert win.findChild(QObject, "reelList").property("count") == 3
    assert not warnings, warnings
    win.close()


def test_desktop_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = desktop.install(python="/py/bin/python")
    text = path.read_text()
    assert 'Exec="/py/bin/python" -m reel_triage app' in text and "Icon=reel-triage" in text
    assert desktop.icon_file().is_file()
    desktop.uninstall()
    assert not path.exists() and not desktop.icon_file().exists()


def test_pull_needs_a_username(backend, qtbot):
    with qtbot.waitSignal(backend.message) as sig:
        backend.pullNew("  ")
    assert "username" in sig.args[0] and not backend.busy
    backend._store.set_setting("instagram_user", "someone")
    backend.reload()
    assert backend.instagramUser == "someone"
