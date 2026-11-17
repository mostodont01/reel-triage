import json
import zipfile

from reel_triage import ids, importer


def test_parse_links_and_codes():
    assert ids.parse("https://www.instagram.com/reel/AbC_12-x/?igsh=xyz") == "AbC_12-x"
    assert ids.parse("https://instagram.com/p/Zz99zz/") == "Zz99zz"
    assert ids.parse("https://www.instagram.com/someone/reel/Qq11qq/") == "Qq11qq"
    assert ids.parse("  AbC_12-x ") == "AbC_12-x"
    assert ids.parse("hello world") is None
    assert ids.parse("--flag") is None
    assert ids.url("AbC") == "https://www.instagram.com/p/AbC/"


def test_tracking_params_are_dropped():
    code = ids.parse("https://www.instagram.com/reel/Df1aaaaaaaa/?srtk=c2VjcmV0")
    assert code == "Df1aaaaaaaa"
    assert "srtk" not in ids.url(code)


def test_find_all_dedupes_in_order():
    text = "x https://www.instagram.com/reel/AAAAAA/ y https://www.instagram.com/p/BBBBBB/ https://www.instagram.com/reel/AAAAAA/"
    assert ids.find_all(text) == ["AAAAAA", "BBBBBB"]


def test_fix_text_undoes_mojibake():
    broken = "PoslednÃ­ letnÃ­"
    assert importer.fix_text(broken) == "Poslední letní"
    assert importer.fix_text("already fine ř") == "already fine ř"


def _export_post(code, ts, caption="", tags=(), name="Author", user="author"):
    return {
        "timestamp": ts,
        "media": [],
        "label_values": [
            {"label": "URL", "value": f"https://www.instagram.com/reel/{code}/",
             "href": f"https://www.instagram.com/reel/{code}/"},
            {"label": "Caption", "value": caption.encode("utf-8").decode("latin-1")},
            {"label": "Title", "value": ""},
            {"dict": [{"dict": [{"label": "Name", "value": t}], "title": ""} for t in tags],
             "title": "Hashtags"},
            {"dict": [{"dict": [{"label": "URL", "value": ""}, {"label": "Name", "value": name},
                                {"label": "Username", "value": user}], "title": ""}],
             "title": "Owner"},
            {"dict": [], "title": "Brand partner"},
        ],
    }


def _collection(name, posts):
    return {
        "timestamp": 1,
        "media": [],
        "label_values": [
            {"label": "Name", "value": name.encode("utf-8").decode("latin-1")},
            {"label": "Type", "value": "Default"},
            {"dict": [{"dict": p["label_values"], "title": ""} for p in posts], "title": ""},
        ],
    }


def test_read_instagram_export_zip(tmp_path):
    a = _export_post("AAAAAA", 1700000000, "Nástroj pro LiDAR", ["robotics"], "Bob", "bob.dev")
    b = _export_post("BBBBBB", 1700000500, "meme")
    only_in_collection = _export_post("CCCCCC", 0, "from a folder")
    z = tmp_path / "instagram-x.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("your_instagram_activity/saved/saved_posts.json", json.dumps([a, b]))
        f.writestr("your_instagram_activity/saved/saved_collections.json",
                   json.dumps([_collection("Robotika", [a, only_in_collection])]))
        f.writestr("your_instagram_activity/likes/liked_posts.json",
                   json.dumps([_export_post("LIKEDX", 5)]))
    out = importer.read(z)
    assert list(out) == ["AAAAAA", "BBBBBB", "CCCCCC"]  # liked posts ignored
    assert out["AAAAAA"] == {
        "caption": "Nástroj pro LiDAR", "hashtags": ["robotics"], "author": "Bob",
        "author_id": "bob.dev", "saved_at": 1700000000, "collections": ["Robotika"],
    }
    assert "collections" not in out["BBBBBB"]
    assert out["CCCCCC"]["collections"] == ["Robotika"]
    assert "saved_at" not in out["CCCCCC"]


def test_read_export_folder(tmp_path):
    d = tmp_path / "export" / "your_instagram_activity" / "saved"
    d.mkdir(parents=True)
    (d / "saved_posts.json").write_text(json.dumps([_export_post("AAAAAA", 10)]))
    assert list(importer.read(tmp_path / "export")) == ["AAAAAA"]


def test_read_unknown_json_walks_for_links(tmp_path):
    f = tmp_path / "saved_old.json"
    f.write_text(json.dumps({"saved": [{"string_map_data": {"x": {
        "href": "https://www.instagram.com/p/OLDOLD/", "timestamp": 42}}}]}))
    assert importer.read(f) == {"OLDOLD": {"saved_at": 42}}


def test_read_text_file(tmp_path):
    f = tmp_path / "links.txt"
    f.write_text("https://www.instagram.com/reel/AAAAAA/?igsh=1\nBBBBBB CCCCCC\n\n")
    assert list(importer.read(f)) == ["AAAAAA", "BBBBBB", "CCCCCC"]
