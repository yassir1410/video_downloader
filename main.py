#!/usr/bin/env python3
"""Minimal Video Downloader for Fedora — Entry Point."""

import logging
import sys

# Configure logging before any application imports
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Suppress overly verbose loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main():
    """Launch the Video Downloader application."""
    logger.info("Starting Video Downloader")

    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
    except ValueError as e:
        print(
            f"Error: Required libraries not found: {e}\n"
            "Please install: sudo dnf install gtk4 libadwaita python3-gobject",
            file=sys.stderr,
        )
        sys.exit(1)

    from app.application import VideoDownloaderApplication

    app = VideoDownloaderApplication()
    exit_code = app.run(sys.argv)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
