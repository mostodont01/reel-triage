import json
import threading
import urllib.request
from urllib.error import HTTPError

import pytest

from reel_triage import cli, server
from conftest import verdict


@pytest.fixture
def running(store):
    store.add("AAAAAA", caption="cap", collections=["robotics"])
    store.add("BBBBBB")
    store.set_verdict("AAAAAA", verdict(verdict="try"))
    store.update("BBBBBB", quick={"category": "humor", "verdict": "keep", "title": "t", "note": "n"})
    (store.path("AAAAAA") / "video.mp4").write_bytes(bytes(range(256)) * 4)
    httpd = server.make_server(store, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield store, f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {})) as r:
        return r.status, dict(r.headers), r.read()


def post(url, data):
    req = urllib.request.Request(url, json.dumps(data).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def test_page_and_api(running):
    store, base = running
    status, headers, body = get(base + "/")
    assert status == 200 and b"Reel Triage" in body
    _, _, body = get(base + "/api/reels")
    reels = {r["id"]: r for r in json.loads(body)}
    assert reels["AAAAAA"]["verdict"]["verdict"] == "try"
    assert reels["AAAAAA"]["collections"] == ["robotics"]
    assert reels["BBBBBB"]["quick"]["verdict"] == "keep" and reels["BBBBBB"]["verdict"] is None


def test_media_and_ranges(running):
    _, base = running
    status, headers, body = get(base + "/media/AAAAAA/video.mp4")
    assert status == 200 and len(body) == 1024 and headers["Content-Type"] == "video/mp4"
    status, headers, body = get(base + "/media/AAAAAA/video.mp4", {"Range": "bytes=10-19"})
    assert status == 206 and body == bytes(range(10, 20)) and headers["Content-Range"] == "bytes 10-19/1024"
    status, _, body = get(base + "/media/AAAAAA/video.mp4", {"Range": "bytes=-4"})
    assert status == 206 and body == bytes(range(252, 256))
    for bad in ("/media/AAAAAA/missing.mp4", "/media/NOPE/video.mp4", "/media/AAAAAA/../../x"):
        with pytest.raises(HTTPError) as e:
            get(base + bad)
        assert e.value.code == 404


def test_pick(running):
    store, base = running
    assert post(base + "/api/pick", {"id": "AAAAAA", "pick": "want"})[1]["ok"]
    assert store.get("AAAAAA")["pick"] == "want"
    post(base + "/api/pick", {"id": "AAAAAA", "pick": None})
    assert store.get("AAAAAA")["pick"] is None
    for bad in ({"id": "AAAAAA", "pick": "love"}, {"id": "NOPE", "pick": "want"}):
        with pytest.raises(HTTPError) as e:
            post(base + "/api/pick", bad)
        assert e.value.code == 400


def test_cli_add_import_status_list(store, tmp_path, capsys):
    cli.main(["add", "https://www.instagram.com/reel/AAAAAA/?igsh=x", "BBBBBB"])
    assert "queued 2 new" in capsys.readouterr().out
    f = tmp_path / "links.txt"
    f.write_text("BBBBBB CCCCCC")
    cli.main(["import", str(f)])
    assert "1 new" in capsys.readouterr().out
    store.set_verdict("AAAAAA", verdict(verdict="try", title="Cool tool"))
    store.update("CCCCCC", quick={"category": "humor", "verdict": "skip", "title": "Meme", "note": ""})
    cli.main(["status"])
    out = capsys.readouterr().out
    assert "3 reels" in out and "try 1" in out and "skip 1" in out
    cli.main(["list", "--verdict", "try"])
    out = capsys.readouterr().out
    assert "Cool tool" in out and "CCCCCC" not in out
    cli.main(["list"])
    assert "q:skip" in capsys.readouterr().out


def test_cli_verdict_and_pick(store, tmp_path, capsys):
    store.add("AAAAAA")
    f = tmp_path / "v.json"
    f.write_text(json.dumps(verdict(verdict="keep")))
    cli.main(["verdict", "AAAAAA", str(f)])
    assert store.verdict("AAAAAA")["model"] == "manual"
    f.write_text(json.dumps({"verdict": "keep"}))
    with pytest.raises(SystemExit):
        cli.main(["verdict", "AAAAAA", str(f)])
    cli.main(["pick", "AAAAAA", "tried"])
    assert store.get("AAAAAA")["pick"] == "tried"
    cli.main(["pick", "AAAAAA", "none"])
    assert store.get("AAAAAA")["pick"] is None
    cli.main(["show", "AAAAAA"])
    assert "Verdict:" in capsys.readouterr().out


def test_cli_rejects_bad_ids(store):
    with pytest.raises(SystemExit):
        cli.main(["add", "not a link"])


def test_page_embeds_data_safely(store):
    store.add("AAAAAA", caption="evil </script><script>alert(1)</script>")
    html = server.page(store).decode()
    assert "/*__REELS__*/" not in html
    assert "</script><script>alert" not in html  # can't close the script tag
    assert '"AAAAAA"' in html
