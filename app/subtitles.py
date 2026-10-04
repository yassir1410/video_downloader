"""Subtitle detection and options generation service."""

import logging
from typing import Optional

from app.models import VideoMetadata

logger = logging.getLogger(__name__)

# Common language code to human-readable names mapping
LANGUAGE_NAMES = {
    "en": "English",
    "ar": "العربية",
    "fr": "Français",
    "es": "Español",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
    "tr": "Türkçe",
    "hi": "हिन्दी",
    "nl": "Nederlands",
    "pl": "Polski",
    "id": "Bahasa Indonesia",
}


class SubtitleService:
    """Handles subtitle detection from metadata and yt-dlp option generation."""

    def get_available_subtitles(
        self, metadata: VideoMetadata
    ) -> list[tuple[str, str, bool]]:
        """Return a sorted list of (lang_code, display_name, is_auto_caption).

        Manual subtitles take priority over automatic captions.
        """
        results: dict[str, tuple[str, str, bool]] = {}

        # 1. Manual subtitles (higher priority)
        manual_subs = metadata.subtitles or {}
        for code in manual_subs:
            clean_code = code.split("-")[0].lower()
            name = LANGUAGE_NAMES.get(clean_code, code)
            results[code] = (code, f"{name} ({code})", False)

        # 2. Automatic captions (if manual not already present for that language)
        auto_subs = metadata.automatic_captions or {}
        for code in auto_subs:
            clean_code = code.split("-")[0].lower()
            if code not in results and clean_code not in results:
                name = LANGUAGE_NAMES.get(clean_code, code)
                results[code] = (code, f"{name} [Auto] ({code})", True)

        # Sort with English first, then alphabetical by name
        def sort_key(item: tuple[str, str, bool]):
            code, name, is_auto = item
            is_english = code.startswith("en")
            return (not is_english, is_auto, name.lower())

        sorted_list = sorted(results.values(), key=sort_key)
        return sorted_list

    def get_subtitle_options(
        self, lang_code: Optional[str], embed: bool = False
    ) -> dict:
        """Generate yt-dlp options for subtitles."""
        if not lang_code or lang_code == "none":
            return {}

        opts: dict = {
            "writesubtitles": True,
            "subtitleslangs": [lang_code],
            "writeautomaticsub": True,
            "subtitlesformat": "srt/best",
        }

        if embed:
            opts["postprocessors"] = [{"key": "FFmpegEmbedSubtitle"}]

        return opts
