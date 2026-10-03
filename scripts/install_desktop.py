#!/usr/bin/env python3
"""Desktop integration installer for Video Downloader."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_ID = "io.github.videodownloader.VideoDownloader"
PROJECT_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python3"
SYSTEM_PYTHON = Path(sys.executable)

PYTHON_EXEC = str(VENV_PYTHON if VENV_PYTHON.exists() else SYSTEM_PYTHON)
MAIN_PY = str(PROJECT_DIR / "main.py")
ICON_SRC = PROJECT_DIR / "assets" / f"{APP_ID}.svg"

USER_HOME = Path.home()
APPS_DIR = USER_HOME / ".local" / "share" / "applications"
ICONS_DIR = USER_HOME / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"

DESKTOP_TEMPLATE = f"""[Desktop Entry]
Name=Video Downloader
GenericName=Video Downloader
Comment=Download videos from the web using yt-dlp
Exec="{PYTHON_EXEC}" "{MAIN_PY}"
Path={PROJECT_DIR}
Icon={APP_ID}
Terminal=false
Type=Application
Categories=AudioVideo;Network;
Keywords=video;download;youtube;yt-dlp;media;
StartupNotify=true
StartupWMClass={APP_ID}
"""


def install():
    print(f"Installing Video Downloader desktop integration for {USER_HOME.name}...")

    # 1. Ensure target directories exist
    APPS_DIR.mkdir(parents=True, exist_ok=True)
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Install icon
    target_icon = ICONS_DIR / f"{APP_ID}.svg"
    print(f"Copying icon: {ICON_SRC} -> {target_icon}")
    shutil.copyfile(ICON_SRC, target_icon)

    # 3. Write desktop file
    target_desktop = APPS_DIR / f"{APP_ID}.desktop"
    print(f"Writing desktop entry -> {target_desktop}")
    with open(target_desktop, "w", encoding="utf-8") as f:
        f.write(DESKTOP_TEMPLATE)

    # Make desktop file executable
    target_desktop.chmod(0o755)

    # 4. Update desktop and icon databases
    print("Updating desktop database...")
    try:
        subprocess.run(["update-desktop-database", str(APPS_DIR)], check=False)
    except FileNotFoundError:
        pass

    print("Updating icon cache...")
    for cache_cmd in ["gtk4-update-icon-cache", "gtk-update-icon-cache"]:
        try:
            subprocess.run([cache_cmd, "-f", "-t", str(USER_HOME / ".local" / "share" / "icons" / "hicolor")], check=False)
            break
        except FileNotFoundError:
            continue

    print("\n✓ Installation complete!")
    print("Video Downloader is now available in your GNOME Applications Menu!")


def uninstall():
    print("Removing Video Downloader desktop integration...")
    target_desktop = APPS_DIR / f"{APP_ID}.desktop"
    target_icon = ICONS_DIR / f"{APP_ID}.svg"

    if target_desktop.exists():
        target_desktop.unlink()
        print(f"Removed {target_desktop}")

    if target_icon.exists():
        target_icon.unlink()
        print(f"Removed {target_icon}")

    try:
        subprocess.run(["update-desktop-database", str(APPS_DIR)], check=False)
    except FileNotFoundError:
        pass

    print("✓ Uninstallation complete.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        uninstall()
    else:
        install()
