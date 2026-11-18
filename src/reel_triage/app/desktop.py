"""Add Reel Triage to the Linux app menu (for the current user).

    reel-triage install-desktop      # menu entry + icon
    reel-triage install-desktop --uninstall

The entry starts the app with this install's Python, so no terminal is needed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import APP_ID, ICON


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def desktop_file() -> Path:
    return data_home() / "applications" / f"{APP_ID}.desktop"


def icon_file() -> Path:
    return data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"


def desktop_entry(python: str) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Reel Triage
GenericName=Saved reels sorter
Comment=Your saved Instagram reels, sorted and reviewed by Claude
Exec="{python}" -m reel_triage app
Icon={APP_ID}
Terminal=false
Categories=Utility;
Keywords=instagram;reels;saved;claude;plugins;
StartupWMClass={APP_ID}
StartupNotify=true
"""


def _refresh() -> None:
    for cmd in (["update-desktop-database", str(desktop_file().parent)],
                ["gtk-update-icon-cache", "-q", "-t", str(data_home() / "icons" / "hicolor")]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, capture_output=True)


def install(python: str | None = None) -> Path:
    desktop_file().parent.mkdir(parents=True, exist_ok=True)
    icon_file().parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON, icon_file())
    desktop_file().write_text(desktop_entry(python or sys.executable), encoding="utf-8")
    _refresh()
    return desktop_file()


def uninstall() -> None:
    desktop_file().unlink(missing_ok=True)
    icon_file().unlink(missing_ok=True)
    _refresh()
