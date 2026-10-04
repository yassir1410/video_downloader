"""Clipboard integration service for detecting video URLs."""

import logging
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from app.utils import extract_urls

logger = logging.getLogger(__name__)


class ClipboardService:
    """Monitors the clipboard when application is active and detects video URLs."""

    def __init__(self):
        self._last_checked_text: Optional[str] = None
        self._dismissed_urls: set[str] = set()

    def check_clipboard(
        self,
        callback: Callable[[list[str]], None],
    ) -> None:
        """Asynchronously read clipboard text and trigger callback with any new URLs.

        Args:
            callback: Called with list of extracted video URLs (main thread).
        """
        display = Gdk.Display.get_default()
        if not display:
            return

        clipboard = display.get_clipboard()

        def on_read_text(source, result):
            try:
                text = clipboard.read_text_finish(result)
                if not text or text == self._last_checked_text:
                    return

                self._last_checked_text = text
                urls = extract_urls(text)

                # Filter out previously dismissed URLs
                new_urls = [u for u in urls if u not in self._dismissed_urls]
                if new_urls:
                    GLib.idle_add(callback, new_urls)
            except Exception as e:
                logger.debug("Could not read clipboard text: %s", e)

        clipboard.read_text_async(None, on_read_text)

    def dismiss_urls(self, urls: list[str]) -> None:
        """Mark URLs as dismissed so user is not prompted again."""
        for u in urls:
            self._dismissed_urls.add(u)

    def clear_dismissed(self) -> None:
        """Clear dismissed URLs cache."""
        self._dismissed_urls.clear()
