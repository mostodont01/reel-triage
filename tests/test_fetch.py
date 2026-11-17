import subprocess

import pytest

from reel_triage import fetch


def test_frame_times():
    assert fetch.frame_times(None, 5) == [0.0]
    assert fetch.frame_times(1.0, 5) == [0.0]
    t = fetch.frame_times(30.0, 5)
    assert t[0] == 1.0 and len(t) == 5 and all(x < 30 for x in t) and t == sorted(t)


def test_describe_uses_first_carousel_item():
    info = {"entries": [{"description": " hi ", "uploader": "Bob", "duration": 12.5}, {}]}
    d = fetch.describe(info)
    assert (d["caption"], d["author"], d["duration"], d["items"]) == ("hi", "Bob", 12.5, 2)


@pytest.fixture
def sample_video(tmp_path):
    """A 3 s test video with a tone, made with the bundled ffmpeg."""
    out = tmp_path / "media.mp4"
    subprocess.run([fetch.ffmpeg(), "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x568:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-shortest",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def test_frames_and_audio(sample_video, tmp_path):
    assert 2.5 < fetch.probe_duration(sample_video) < 3.5
    frames = fetch.extract_frames(sample_video, tmp_path / "frames", count=3)
    assert len(frames) == 3 and all(f.stat().st_size > 0 for f in frames)
    audio = fetch.load_audio(sample_video)
    assert audio is not None and 40000 < len(audio) < 56000


def test_fetch_pipeline_offline(store, sample_video, monkeypatch):
    """The whole fetch step with the network and Whisper faked."""
    store.add("AAAAAA", caption="from the export", author="Export Name")

    def fake_download(code, folder, cookies_from=None):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "media.mp4").write_bytes(sample_video.read_bytes())
        return {"description": "from yt-dlp", "uploader": "yt", "upload_date": "20261117", "like_count": 5}

    monkeypatch.setattr(fetch, "download", fake_download)
    monkeypatch.setattr(fetch, "transcribe", lambda video, model="small": ("you need this plugin", "en"))
    meta = fetch.fetch(store, "AAAAAA", log=lambda *_: None)
    assert meta["status"] == "fetched" and meta["kind"] == "video" and meta["video"] == "video.mp4"
    assert meta["caption"] == "from the export" and meta["author"] == "Export Name"
    assert meta["posted"] == "20261117" and meta["duration"] == pytest.approx(3, abs=0.5)
    assert len(meta["frames"]) >= 3
    assert (store.path("AAAAAA") / "transcript.txt").read_text().strip() == "you need this plugin"


def test_fetch_failure_is_recorded(store, monkeypatch):
    store.add("AAAAAA")

    def boom(*a, **k):
        raise fetch.FetchError("Requested content is not available")

    monkeypatch.setattr(fetch, "download", boom)
    meta = fetch.fetch(store, "AAAAAA", log=lambda *_: None)
    assert meta["status"] == "failed" and "not available" in meta["error"]


def test_photo_post_is_reviewable(store, monkeypatch):
    store.add("AAAAAA", caption="a photo with a tip")

    def no_video(*a, **k):
        raise fetch.FetchError("[Instagram] AAAAAA: No video formats found!")

    monkeypatch.setattr(fetch, "download", no_video)
    meta = fetch.fetch(store, "AAAAAA", log=lambda *_: None)
    assert meta["status"] == "fetched" and meta["kind"] == "text" and meta["frames"] == []
    assert [m["id"] for m in store.to_review()] == ["AAAAAA"]
