"""Download history persistence service."""

import json
import logging
import os
from typing import Optional

from app.models import HistoryItem

logger = logging.getLogger(__name__)

HISTORY_FILE = os.path.expanduser("~/.config/video-downloader/history.json")


class HistoryService:
    """Manages persistent download history."""

    def __init__(self, filepath: str = HISTORY_FILE):
        self._filepath = filepath

    def get_items(self) -> list[HistoryItem]:
        """Load and return all history items, newest first."""
        if not os.path.exists(self._filepath) or os.path.getsize(self._filepath) == 0:
            return []

        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            items = []
            for d in data:
                items.append(
                    HistoryItem(
                        id=d.get("id", ""),
                        title=d.get("title", ""),
                        url=d.get("url", ""),
                        provider=d.get("provider", "Other"),
                        date=d.get("date", ""),
                        filepath=d.get("filepath", ""),
                        output_format=d.get("output_format", "MP4"),
                        quality=d.get("quality", "Best"),
                        filesize=d.get("filesize"),
                    )
                )
            return items
        except Exception as e:
            logger.error("Failed to load history from %s: %s", self._filepath, e)
            return []

    def add_item(self, item: HistoryItem) -> None:
        """Add an item to history and save."""
        items = self.get_items()
        # Remove existing if same ID
        items = [i for i in items if i.id != item.id]
        # Prepend
        items.insert(0, item)
        # Cap at 200 items
        items = items[:200]
        self._save(items)

    def remove_item(self, item_id: str) -> None:
        """Remove a specific item by ID."""
        items = self.get_items()
        items = [i for i in items if i.id != item_id]
        self._save(items)

    def clear_history(self) -> None:
        """Remove all history entries."""
        self._save([])

    def _save(self, items: list[HistoryItem]) -> None:
        """Persist items to disk."""
        try:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
            data = []
            for item in items:
                data.append({
                    "id": item.id,
                    "title": item.title,
                    "url": item.url,
                    "provider": item.provider,
                    "date": item.date,
                    "filepath": item.filepath,
                    "output_format": item.output_format,
                    "quality": item.quality,
                    "filesize": item.filesize,
                })
            tmp_file = self._filepath + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, self._filepath)
        except Exception as e:
            logger.error("Failed to save history to %s: %s", self._filepath, e)
