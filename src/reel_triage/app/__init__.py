"""The desktop app:  reel-triage app   (PySide6 + QML, VL's theme)."""

import sys
from pathlib import Path

QML_DIR = Path(__file__).parent / "qml"
ICON = Path(__file__).parent / "assets" / "reel-triage.svg"
APP_ID = "reel-triage"


def create_engine(backend):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    # The engine owns the backend, so on shutdown the QML goes first and no
    # binding ever sees a missing "reels" object.
    backend.setParent(engine)
    engine.rootContext().setContextProperty("app", backend)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    return engine


def main(argv: list[str] | None = None, store=None) -> int:
    from PySide6.QtCore import QLoggingCategory
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQuickControls2 import QQuickStyle

    from .backend import Backend

    # Same setup as VL and School Notes: Fusion everywhere, quiet Wayland warnings.
    QLoggingCategory.setFilterRules("qt.qpa.wayland.textinput=false\nqt.multimedia.*=false")
    QQuickStyle.setStyle("Fusion")
    app = QGuiApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Reel Triage")
    app.setDesktopFileName(APP_ID)  # matches reel-triage.desktop
    app.setWindowIcon(QIcon(str(ICON)))

    backend = Backend(store)
    engine = create_engine(backend)
    if not engine.rootObjects():
        return 1
    app.aboutToQuit.connect(backend.shutdown)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
