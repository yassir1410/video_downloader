# Video Downloader

A fast, native, minimalist video downloader for Fedora, powered by yt-dlp.

> Paste URL → choose quality → download.

## Features

- Native GTK4/Libadwaita UI — looks and feels like a real GNOME app
- Download videos in MP4 or WebM format
- Extract audio as MP3, M4A, or Opus
- Automatic detection of available video qualities
- Handles YouTube's split video/audio streams (FFmpeg merge)
- Download progress with speed and ETA
- Cancel active downloads
- Desktop notifications on completion
- Dark/light theme support (follows system)
- Supports any website that yt-dlp supports

## Supported Platforms

- **YouTube**: standard videos, `youtu.be` links, Shorts, and high-resolution split streams (1080p, 1440p, 4K).
- **Facebook**: regular posts with videos, Facebook Watch links, Facebook Reels, and `fb.watch` short links.
- **Additional websites**: Any public video source supported by `yt-dlp` (Vimeo, Dailymotion, etc.) works through the same universal pipeline.

## Requirements

- Fedora Linux with GNOME desktop
- Python 3.10+
- GTK4 and Libadwaita
- PyGObject
- FFmpeg (full version from RPM Fusion for best codec support)
- yt-dlp

## Setup on Fedora

### 1. Install system dependencies

```bash
sudo dnf install python3 python3-pip gtk4 libadwaita python3-gobject
```

### 2. Install FFmpeg (full version recommended)

```bash
# Enable RPM Fusion
sudo dnf install \
  https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
  https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm

# Install full FFmpeg
sudo dnf swap ffmpeg-free ffmpeg --allowerasing
```

### 3. Set up Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
source .venv/bin/activate
python main.py
```

## Desktop Integration (Applications Menu)

To integrate Video Downloader into your GNOME desktop and application menu:

```bash
python3 scripts/install_desktop.py
```

This installs the desktop launcher into `~/.local/share/applications/` and the high-resolution vector icon into `~/.local/share/icons/hicolor/scalable/apps/`, making it launchable directly from the GNOME Dash and Application Grid.

To uninstall from the menu:
```bash
python3 scripts/install_desktop.py --uninstall
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+L | Focus URL field |
| Ctrl+O | Choose destination folder |
| Ctrl+Q | Quit |
| Enter | Fetch video info (in URL field) |

## Project Structure

```
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
├── app/
│   ├── __init__.py          # Package marker, version
│   ├── application.py       # Adw.Application subclass
│   ├── window.py            # Main window UI and state machine
│   ├── downloader.py        # Download service (yt-dlp integration)
│   ├── metadata.py          # Metadata extraction service
│   ├── formats.py           # Format detection and selection
│   ├── models.py            # Dataclasses and enums
│   ├── settings.py          # Settings persistence (JSON)
│   └── utils.py             # Formatting utilities
├── assets/
│   ├── icon.svg             # Application icon
│   └── placeholder.svg      # Thumbnail placeholder
├── data/
│   └── *.desktop            # Desktop entry file
└── tests/
    ├── test_utils.py         # Utility function tests
    ├── test_formats.py       # Format service tests
    └── test_metadata.py      # Metadata service tests
```

## Legal Notice

This application is intended for downloading content that the user has permission to download. Users are responsible for complying with applicable copyright laws and the terms of the services they use.

## License

GPL-3.0
# video_downloader
