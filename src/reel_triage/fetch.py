"""Fetch a reel: download it, pull a few frames and transcribe the audio.

Everything runs locally: yt-dlp for the download, ffmpeg from the
imageio-ffmpeg wheel (no system install / root needed) and faster-whisper on
the CPU for the transcript.
"""

import os
import subprocess
from pathlib import Path

from . import ids
from .store import Store

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


class FetchError(Exception):
    pass


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


# --- download -----------------------------------------------------------
def _ydl_opts(folder: Path, cookies_from: str | None) -> dict:
    opts = {
        "outtmpl": str(folder / "media%(playlist_index&_{}|)s.%(ext)s"),
        "format": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg(),
        "writethumbnail": True,
        "ignore_no_formats_error": True,  # photo posts: keep caption + image
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
    }
    if cookies_from:
        opts["cookiesfrombrowser"] = (cookies_from,)
    return opts


def download(code: str, folder: Path, cookies_from: str | None = None) -> dict:
    """Download into folder; return the info dict (caption etc.)."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    folder.mkdir(parents=True, exist_ok=True)
    try:
        with YoutubeDL(_ydl_opts(folder, cookies_from)) as ydl:
            info = ydl.extract_info(ids.url(code), download=True)
    except DownloadError as e:
        raise FetchError(str(e).removeprefix("ERROR: ")) from None
    return info or {}


def peek(code: str, cookies_from: str | None = None) -> dict:
    """The post's info (caption, author, ...) without downloading anything."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "ignore_no_formats_error": True, "retries": 2}
    if cookies_from:
        opts["cookiesfrombrowser"] = (cookies_from,)
    try:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(ids.url(code), download=False) or {}
    except DownloadError as e:
        raise FetchError(str(e).removeprefix("ERROR: ")) from None


def _first(info: dict, key: str):
    """A field from the post, or from its first carousel item."""
    if info.get(key):
        return info[key]
    for entry in info.get("entries") or []:
        if entry and entry.get(key):
            return entry[key]
    return None


def describe(info: dict) -> dict:
    caption = _first(info, "description") or ""
    return {
        "author": _first(info, "uploader") or _first(info, "channel") or "",
        "author_id": _first(info, "uploader_id") or _first(info, "channel") or "",
        "caption": caption.strip(),
        "duration": _first(info, "duration"),
        "posted": _first(info, "upload_date"),  # YYYYMMDD
        "likes": _first(info, "like_count"),
        "items": len(info.get("entries") or []) or 1,
    }


def media_files(folder: Path) -> tuple[list[Path], list[Path]]:
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name.startswith("media"))
    videos = [p for p in files if p.suffix.lower() in VIDEO_EXTS]
    images = [p for p in files if p.suffix.lower() in IMAGE_EXTS]
    return videos, images


# --- frames -------------------------------------------------------------
def probe_duration(video: Path) -> float | None:
    proc = subprocess.run([ffmpeg(), "-i", str(video)], capture_output=True, text=True)
    for line in proc.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            h, m, s = line.split(",")[0].split()[1].split(":")
            try:
                return int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                return None
    return None


def frame_times(duration: float | None, count: int) -> list[float]:
    """Times to grab: ~1 s in (titles usually show there), then spread out."""
    if not duration or duration <= 1.5:
        return [0.0]
    times = [min(1.0, duration / 4)]
    for k in range(1, count):
        times.append(round(duration * k / count + duration / (2 * count), 2))
    return sorted({min(t, duration - 0.2) for t in times})


def extract_frames(video: Path, out: Path, count: int = 5, duration: float | None = None) -> list[Path]:
    out.mkdir(exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()
    frames = []
    for i, t in enumerate(frame_times(duration or probe_duration(video), count)):
        target = out / f"{i + 1:02d}_{t:05.1f}s.jpg"
        subprocess.run(
            [ffmpeg(), "-loglevel", "error", "-y", "-ss", str(t), "-i", str(video),
             "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "4", str(target)],
            check=False, capture_output=True,
        )
        if target.is_file():
            frames.append(target)
    return frames


# --- transcript ---------------------------------------------------------
_models: dict[str, object] = {}


def load_audio(video: Path):
    """16 kHz mono float32 samples via ffmpeg (avoids PyAV version issues).
    None if the file has no audio."""
    import numpy as np

    proc = subprocess.run(
        [ffmpeg(), "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1",
         "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0


def transcribe(video: Path, model: str = "small") -> tuple[str, str | None]:
    """(text, language). Empty text for reels without speech."""
    from faster_whisper import WhisperModel

    audio = load_audio(video)
    if audio is None or len(audio) < 16000 // 2:
        return "", None
    if model not in _models:
        threads = max(1, (os.cpu_count() or 4) - 1)
        _models[model] = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
    segments, info = _models[model].transcribe(audio, vad_filter=True, beam_size=1)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, (info.language if text else None)


# --- all together -------------------------------------------------------
def fetch(store: Store, code: str, model: str = "small", cookies_from: str | None = None,
          keep_video: bool = True, log=print) -> dict:
    folder = store.path(code)
    try:
        info = download(code, folder, cookies_from)
    except FetchError as e:
        if "no video formats" in str(e).lower():
            # A photo post: nothing to download, but the export's caption can
            # still be reviewed.
            (folder / "transcript.txt").write_text("\n", encoding="utf-8")
            log("  no video (photo post): reviewing from the caption")
            return store.update(code, status="fetched", error=None, kind="text", video=None,
                                poster=None, frames=[], language=None)
        log(f"  download failed: {e}")
        return store.update(code, status="failed", error=str(e)[:500])

    meta = describe(info)
    known = store.get(code)
    for key in ("author", "author_id", "caption"):  # the export's values are better
        if known.get(key):
            meta.pop(key)
    videos, images = media_files(folder)
    frames_dir = folder / "frames"
    frames: list[Path] = []
    transcript, language = "", None
    if videos:
        video = videos[0]
        if video.name != "video.mp4" and video.suffix == ".mp4":
            video = video.rename(folder / "video.mp4")
        duration = meta["duration"] or probe_duration(video)
        meta["duration"] = round(duration, 1) if duration else None
        frames = extract_frames(video, frames_dir, duration=duration)
        log(f"  {len(frames)} frames, transcribing…")
        transcript, language = transcribe(video, model)
        if not keep_video:
            video.unlink()
    elif images:
        frames_dir.mkdir(exist_ok=True)
        for i, img in enumerate(images[:5]):
            target = frames_dir / f"{i + 1:02d}_image.jpg"
            subprocess.run([ffmpeg(), "-loglevel", "error", "-y", "-i", str(img),
                            "-vf", "scale=540:-2", str(target)], capture_output=True)
            if target.is_file():
                frames.append(target)

    (folder / "transcript.txt").write_text(transcript + "\n", encoding="utf-8")
    meta.update(
        status="fetched",
        error=None,
        kind="video" if videos else ("image" if images else "text"),
        video="video.mp4" if videos and keep_video else None,
        poster=next((p.name for p in images), None),
        frames=[f"frames/{p.name}" for p in frames],
        language=language,
    )
    return store.update(code, **meta)
