"""Metadata extraction service using yt-dlp."""

import logging
from typing import Optional

import yt_dlp

from app.models import VideoMetadata

logger = logging.getLogger(__name__)


class MetadataError(Exception):
    """Raised when metadata extraction fails."""

    def __init__(self, message: str, technical_detail: str = ""):
        super().__init__(message)
        self.user_message = message
        self.technical_detail = technical_detail


class MetadataService:
    """Extracts video metadata using yt-dlp without downloading."""

    def extract(self, url: str) -> VideoMetadata:
        """Extract video metadata from a URL.

        Args:
            url: The video URL to extract metadata from.

        Returns:
            VideoMetadata dataclass with extracted information.

        Raises:
            MetadataError: If extraction fails with a user-friendly message.
        """
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": False,
            "no_color": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if info is None:
                raise MetadataError(
                    "Could not retrieve video information.",
                    "extract_info returned None",
                )

            return VideoMetadata(
                title=info.get("title", "Unknown Title"),
                uploader=info.get("uploader") or info.get("channel") or info.get("uploader_id") or "Unknown",
                duration=int(info.get("duration", 0)),
                thumbnail_url=info.get("thumbnail", ""),
                webpage_url=info.get("webpage_url", url),
                raw_formats=info.get("formats", []),
            )

        except MetadataError:
            raise

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            user_message = self._classify_error(error_msg)
            logger.error("yt-dlp DownloadError for %s: %s", url, e)
            raise MetadataError(user_message, str(e)) from e

        except yt_dlp.utils.ExtractorError as e:
            logger.error("yt-dlp ExtractorError for %s: %s", url, e)
            raise MetadataError(
                "Unable to extract information from this URL.",
                str(e),
            ) from e

        except Exception as e:
            logger.error("Unexpected error extracting metadata for %s: %s", url, e)
            raise MetadataError(
                "An unexpected error occurred while fetching video information.",
                str(e),
            ) from e

    def _classify_error(self, error_msg: str) -> str:
        """Convert yt-dlp error messages into user-friendly messages."""
        if "private" in error_msg:
            return "This video is private and cannot be accessed."
        if "geo" in error_msg or "country" in error_msg:
            return "This video is not available in your region."
        if "age" in error_msg or "sign in" in error_msg or "login" in error_msg:
            return (
                "This video requires authentication.\n"
                "Age-restricted or login-required videos are not supported in this version."
            )
        if "removed" in error_msg or "deleted" in error_msg:
            return "This video has been removed."
        if "copyright" in error_msg:
            return "This video is unavailable due to a copyright claim."
        if "live" in error_msg and "stream" in error_msg:
            return "Live streams cannot be downloaded."
        if "unavailable" in error_msg or "not available" in error_msg:
            return "This video is unavailable."
        if "unsupported" in error_msg or "no suitable" in error_msg:
            return (
                "This URL is not supported.\n"
                "Please check the URL and try again."
            )
        if "network" in error_msg or "connection" in error_msg or "timed out" in error_msg:
            return (
                "Network error.\n"
                "Please check your internet connection and try again."
            )
        return (
            "Unable to access this video.\n"
            "The video may be private, unavailable, or require authentication."
        )
