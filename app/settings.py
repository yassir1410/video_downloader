"""Application settings persistence."""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "download_dir": str(Path.home() / "Downloads"),
    "default_quality": "Best",
    "default_format": "MP4",
    "default_mode": "Video + Audio",
    "notifications_enabled": True,
}


class Settings:
    """Manages application settings with JSON persistence."""

    def __init__(self):
        self._config_dir = Path.home() / ".config" / "video-downloader"
        self._config_file = self._config_dir / "settings.json"
        self._data: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        """Load settings from disk."""
        if not self._config_file.exists():
            logger.debug("No settings file found, using defaults.")
            return

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                stored = json.load(f)
            # Merge with defaults so new keys get default values
            for key, default_value in DEFAULT_SETTINGS.items():
                self._data[key] = stored.get(key, default_value)
            logger.info("Settings loaded from %s", self._config_file)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load settings, using defaults: %s", e)

    def save(self) -> None:
        """Save current settings to disk."""
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            logger.debug("Settings saved to %s", self._config_file)
        except OSError as e:
            logger.error("Failed to save settings: %s", e)

    def get(self, key: str) -> Any:
        """Get a setting value."""
        return self._data.get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Set a setting value and save."""
        self._data[key] = value
        self.save()

    @property
    def download_dir(self) -> str:
        return self._data.get("download_dir", DEFAULT_SETTINGS["download_dir"])

    @download_dir.setter
    def download_dir(self, path: str) -> None:
        self.set("download_dir", path)

    @property
    def default_quality(self) -> str:
        return self._data.get("default_quality", DEFAULT_SETTINGS["default_quality"])

    @property
    def default_format(self) -> str:
        return self._data.get("default_format", DEFAULT_SETTINGS["default_format"])

    @property
    def default_mode(self) -> str:
        return self._data.get("default_mode", DEFAULT_SETTINGS["default_mode"])

    @property
    def notifications_enabled(self) -> bool:
        return self._data.get("notifications_enabled", True)
