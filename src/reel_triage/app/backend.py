"""The app's Python side: the reel list, filters, the selected reel, picks,
getting new reels in and running the sort / review pipeline."""

import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QObject, QProcess,
                            QProcessEnvironment, Qt, QTimer, QUrl, Property, Signal, Slot)
from PySide6.QtGui import QGuiApplication

from .. import feed, ids, importer, server, usage
from ..store import PICKS, Store

LOG_LINES = 400


def _file_url(store: Store, code: str, name: str | None) -> str:
    if not name:
        return ""
    path = store.path(code) / name
    return QUrl.fromLocalFile(str(path)).toString() if path.is_file() else ""


def _thumb(store: Store, r: dict) -> str:
    return _file_url(store, r["id"], r.get("poster")) or _file_url(store, r["id"], (r.get("frames") or [None])[0])


class ReelList(QAbstractListModel):
    ROLES = ["reelId", "title", "verdict", "verdictLabel", "category", "quality", "author",
             "thumb", "pick", "reviewed", "saved"]

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store = store
        self._rows: list[dict] = []

    def roleNames(self):
        return {Qt.UserRole + i: QByteArray(n.encode()) for i, n in enumerate(self.ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        r = self._rows[index.row()]
        name = self.ROLES[role - Qt.UserRole] if role >= Qt.UserRole else "title"
        k = feed.vkey(r)
        if name == "reelId":
            return r["id"]
        if name == "title":
            return feed.title(r)
        if name == "verdict":
            return k
        if name == "verdictLabel":
            return feed.LABEL.get(k, k)
        if name == "category":
            return feed.category(r)
        if name == "quality":
            return (r.get("verdict") or {}).get("quality") or 0
        if name == "author":
            return r.get("author") or r.get("author_id") or ""
        if name == "thumb":
            return _thumb(self._store, r)
        if name == "pick":
            return r.get("pick") or ""
        if name == "reviewed":
            return bool(r.get("verdict"))
        if name == "saved":
            t = r.get("saved_at") or r.get("added")
            return datetime.fromtimestamp(t).strftime("%Y-%m-%d") if t else ""
        return None

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rows(self) -> list[dict]:
        return self._rows

    def row_of(self, code: str) -> int:
        return next((i for i, r in enumerate(self._rows) if r["id"] == code), -1)

    def changed(self, code: str) -> None:
        i = self.row_of(code)
        if i >= 0:
            self.dataChanged.emit(self.index(i), self.index(i))


class Backend(QObject):
    filtersChanged = Signal()
    dataChanged = Signal()
    currentChanged = Signal()
    busyChanged = Signal()
    logChanged = Signal()
    usageChanged = Signal()
    message = Signal(str)  # a short toast

    def __init__(self, store: Store | None = None, parent=None):
        super().__init__(parent)
        self._store = store or Store()
        self._reels: list[dict] = []
        self._model = ReelList(self._store, self)
        self._verdict, self._pick, self._category, self._search, self._sort = "", "", "", "", "best"
        self._current: dict | None = None
        self._log: list[str] = []
        self._proc: QProcess | None = None
        self._queue: list[list[str]] = []
        self._live_usage: dict | None = None
        self._live_at = 0.0
        self._usage = {}
        self.reload()
        self.refreshUsage()
        self._usage_timer = QTimer(self, interval=60_000, timeout=self.refreshUsage)
        self._usage_timer.start()

    # -- data ---------------------------------------------------------------

    @Slot()
    def reload(self):
        keep = self._current["id"] if self._current else None
        self._reels = server.reels_json(self._store)
        self._apply()
        if keep:
            self.select(keep)
        self.dataChanged.emit()

    def _apply(self) -> None:
        rows = [r for r in self._reels
                if feed.matches(r, self._verdict, self._category, self._pick, self._search)]
        self._model.set_rows(feed.ordered(rows, self._sort))
        self.filtersChanged.emit()

    def _find(self, code: str) -> dict | None:
        return next((r for r in self._reels if r["id"] == code), None)

    @Property(QObject, constant=True)
    def reels(self):
        return self._model

    @Property("QVariantMap", notify=dataChanged)
    def counts(self):
        return feed.counts(self._reels)

    @Property("QVariantList", notify=dataChanged)
    def categories(self):
        return [{"name": n, "count": c} for n, c in feed.categories(self._reels)]

    @Property("QVariantList", constant=True)
    def verdictFilters(self):
        return [{"key": k, "label": label} for k, label in feed.VERDICTS]

    @Property("QVariantList", constant=True)
    def pickFilters(self):
        return [{"key": k, "label": label} for k, label in feed.PICK_FILTERS]

    @Property(str, constant=True)
    def dataFolder(self):
        return str(self._store.root)

    # -- filters ------------------------------------------------------------

    @Property(str, notify=filtersChanged)
    def verdictFilter(self):
        return self._verdict

    @Property(str, notify=filtersChanged)
    def pickFilter(self):
        return self._pick

    @Property(str, notify=filtersChanged)
    def categoryFilter(self):
        return self._category

    @Property(str, notify=filtersChanged)
    def search(self):
        return self._search

    @Property(str, notify=filtersChanged)
    def sortMode(self):
        return self._sort

    @Property(int, notify=filtersChanged)
    def matchCount(self):
        return self._model.rowCount()

    @Slot(str)
    def setVerdictFilter(self, key: str):
        self._verdict = key
        self._apply()

    @Slot(str)
    def setPickFilter(self, key: str):
        self._pick = key
        self._apply()

    @Slot(str)
    def setCategoryFilter(self, name: str):
        self._category = "" if name == self._category else name
        self._apply()

    @Slot(str)
    def setSearch(self, text: str):
        self._search = text.strip()
        self._apply()

    @Slot(str)
    def setSortMode(self, mode: str):
        self._sort = mode if mode in ("best", "new") else "best"
        self._apply()

    # -- the selected reel ----------------------------------------------------

    @Property("QVariantMap", notify=currentChanged)
    def current(self):
        return self._detail(self._current) if self._current else {}

    @Property(int, notify=currentChanged)
    def currentRow(self):
        return self._model.row_of(self._current["id"]) if self._current else -1

    @Slot(str)
    def select(self, code: str):
        self._current = self._find(code)
        self.currentChanged.emit()

    @Slot(int)
    def selectRow(self, row: int):
        rows = self._model.rows()
        self.select(rows[row]["id"] if 0 <= row < len(rows) else "")

    def _detail(self, r: dict) -> dict:
        v = r.get("verdict") or {}
        quick = r.get("quick") or {}
        k = feed.vkey(r)
        tool = v.get("tool") or {}
        posted = r.get("posted") or ""
        frames = [{"url": _file_url(self._store, r["id"], f), "time": feed.frame_time(f) or 0.0}
                  for f in r.get("frames") or []]
        safe = lambda u: u if isinstance(u, str) and u.lower().startswith(("http://", "https://")) else ""
        if v:
            note = ""
        elif r.get("status") == "failed":
            note = "Download failed: " + (r.get("error") or "")
        elif quick:
            note = ("Sorted from the caption only; a full review (video, transcript, web check) is next."
                    if quick.get("verdict") == "deep" else "Sorted from the caption only.")
        elif r.get("status") == "fetched":
            note = "Downloaded, waiting for Claude's review."
        else:
            note = "Queued: not downloaded or sorted yet."
        return {
            "id": r["id"],
            "title": feed.title(r),
            "verdict": k,
            "verdictLabel": feed.LABEL.get(k, k),
            "reviewed": bool(v),
            "category": feed.category(r),
            "quality": v.get("quality") or 0,
            "comment": v.get("comment") or quick.get("note") or "",
            "summary": v.get("summary") or "",
            "action": v.get("action") or "",
            "tool": {
                "name": tool.get("name") or "",
                "url": safe(tool.get("url")),
                "stars": str(tool.get("stars") or ""),
                "lastUpdate": str(tool.get("last_update") or ""),
                "alreadyHave": bool(tool.get("already_have")),
                "builtIn": bool(tool.get("built_in")),
                "safety": tool.get("safety") or "",
            },
            "projects": list(v.get("projects") or []),
            "links": [u for u in map(safe, v.get("links") or []) if u],
            "note": note,
            "caption": r.get("caption") or "",
            "author": r.get("author") or r.get("author_id") or "",
            "posted": f"{posted[:4]}-{posted[4:6]}-{posted[6:]}" if len(posted) == 8 else "",
            "url": r.get("url") or ids.url(r["id"]),
            "video": _file_url(self._store, r["id"], r.get("video")),
            "poster": _thumb(self._store, r),
            "frames": frames,
            "collections": list(r.get("collections") or []),
            "pick": r.get("pick") or "",
        }

    # -- picks ----------------------------------------------------------------

    @Slot(str, str)
    def setPick(self, code: str, pick: str):
        r = self._find(code)
        if r is None or (pick and pick not in PICKS):
            return
        new = None if (not pick or r.get("pick") == pick) else pick  # clicking again clears it
        self._store.set_pick(code, new)
        r["pick"] = new
        self._model.changed(code)
        self.dataChanged.emit()
        if self._current and self._current["id"] == code:
            self.currentChanged.emit()
        if new == "want":
            self.message.emit("Marked to implement. Say /reels in Claude Code to install it.")

    @Slot(str)
    def copy(self, text: str):
        QGuiApplication.clipboard().setText(text)
        self.message.emit("Copied")

    # -- getting new reels in -------------------------------------------------

    @Slot(str, result=str)
    def addLinks(self, text: str) -> str:
        codes = ids.find_all(text)
        if not codes:
            return "No Instagram links found."
        new = sum(self._store.add(c, "manual") for c in codes)
        self.reload()
        return f"Added {new} new reel{'s' if new != 1 else ''}" + (
            f" ({len(codes) - new} already known)" if len(codes) > new else "") + "."

    @Slot(str, result=str)
    def importExport(self, path_or_url: str) -> str:
        path = Path(QUrl(path_or_url).toLocalFile() if path_or_url.startswith("file:") else path_or_url)
        try:
            found = importer.read(path)
        except Exception as e:  # a bad zip or JSON: tell the user, don't crash
            return f"Couldn't read {path.name}: {e}"
        new = sum(self._store.add(c, f"import:{path.name}", **info) for c, info in found.items())
        self.reload()
        return f"{path.name}: {len(found)} saved posts, {new} new."

    # -- the pipeline -----------------------------------------------------------

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._proc is not None

    @Property(str, notify=logChanged)
    def log(self):
        return "\n".join(self._log)

    @Property(int, notify=dataChanged)
    def pending(self):
        """Reels the pipeline would still work on: unsorted, or worth a full review."""
        return sum(1 for r in self._reels if feed.vkey(r) in ("check", "wait"))

    @Slot()
    def runPipeline(self):
        self._start([["sort"], ["run"]])

    @Property(str, notify=dataChanged)
    def instagramUser(self):
        return self._store.settings().get("instagram_user", "")

    @Slot(str)
    def pullNew(self, user: str):
        """Claude reads the newest saves (Borrowed Hands window), then sort + review."""
        user = user.strip().lstrip("@")
        if not user:
            self.message.emit("Enter your Instagram username first")
            return
        self._start([["pull", "--user", user], ["sort"], ["run"]])

    def _start(self, steps: list[list[str]]) -> None:
        if self._proc is not None:
            return
        self._log = []
        self._queue = steps
        self._next_step()
        self.busyChanged.emit()

    @Slot()
    def stopPipeline(self):
        self._queue = []
        if self._proc is not None:
            self._append("stopping…")
            self._proc.terminate()

    def _next_step(self) -> None:
        if not self._queue:
            self._proc = None
            self.busyChanged.emit()
            self.reload()
            self.message.emit("Sort & review finished")
            return
        args = self._queue.pop(0)
        self._append(f"$ reel-triage {' '.join(args)}")
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("REEL_TRIAGE_HOME", str(self._store.root))
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._read(proc))
        proc.finished.connect(lambda code, status: self._finished(proc, code))
        self._proc = proc
        proc.start(sys.executable, ["-m", "reel_triage", *args])

    def _read(self, proc: QProcess) -> None:
        text = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self._append(line)
                live = usage.from_log_line(line)
                if live:
                    self._live_usage, self._live_at = live, time.time()
                    self.refreshUsage()

    def _finished(self, proc: QProcess, code: int) -> None:
        self._read(proc)
        if code != 0:
            self._append(f"(stopped, exit code {code})")
            self._queue = []
        proc.deleteLater()
        self.reload()  # show what's done so far
        self._next_step()

    def _append(self, line: str) -> None:
        self._log.append(line)
        del self._log[:-LOG_LINES]
        self.logChanged.emit()

    @Slot()
    def shutdown(self):
        if self._proc is not None:
            self._queue = []
            self._proc.terminate()
            if not self._proc.waitForFinished(3000):
                self._proc.kill()

    # -- usage -----------------------------------------------------------------

    @Property("QVariantMap", notify=usageChanged)
    def usage(self):
        return self._usage

    @Slot()
    def refreshUsage(self):
        self._usage = usage.merge(usage.load_statusbar(), self._live_usage, self._live_at)
        self.usageChanged.emit()

