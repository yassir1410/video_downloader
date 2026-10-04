"""Download service using yt-dlp."""

import logging
import os
import shutil
import threading
from typing import Callable, Optional

import yt_dlp

from app.formats import FormatService
from app.models import DownloadMode, DownloadProgress

logger = logging.getLogger(__name__)


class DownloadCancelled(Exception):
    """Raised when a download is cancelled by the user."""


class DownloadError(Exception):
    """Raised when a download fails."""

    def __init__(self, message: str, technical_detail: str = ""):
        super().__init__(message)
        self.user_message = message
        self.technical_detail = technical_detail


class DownloaderService:
    """Manages video/audio downloads using yt-dlp.

    All public methods are designed to be called from a background thread.
    The progress_callback is called from the background thread — callers
    must dispatch UI updates via GLib.idle_add or similar.
    """

    def __init__(self):
        self._cancel_event = threading.Event()
        self._format_service = FormatService()
        self._current_process: Optional[yt_dlp.YoutubeDL] = None

    def download(
        self,
        url: str,
        quality: str,
        output_format: str,
        mode: DownloadMode,
        destination: str,
        progress_callback: Callable[[DownloadProgress], None],
        clip_start: Optional[str] = None,
        clip_end: Optional[str] = None,
        subtitles_lang: Optional[str] = None,
        embed_subtitles: bool = False,
    ) -> str:
        """Download a video or audio from URL.

        Args:
            url: The video URL.
            quality: Quality label (e.g., "Best", "1080p").
            output_format: Output format (e.g., "MP4", "MP3").
            mode: Download mode (VIDEO_AUDIO or AUDIO_ONLY).
            destination: Destination directory path.
            progress_callback: Called with DownloadProgress updates.
            clip_start: Optional start timestamp (e.g. "00:01:00").
            clip_end: Optional end timestamp (e.g. "00:02:30").
            subtitles_lang: Optional language code for subtitles.
            embed_subtitles: Whether to embed subtitles into output file.

        Returns:
            Path to the downloaded file.

        Raises:
            DownloadCancelled: If the download was cancelled.
            DownloadError: If the download fails.
        """
        self._cancel_event.clear()

        # Verify FFmpeg
        if not self._check_ffmpeg():
            raise DownloadError(
                "FFmpeg is not installed.\n"
                "FFmpeg is required for merging video and audio streams.\n"
                "Install it with: sudo dnf install ffmpeg",
                "ffmpeg not found in PATH",
            )

        # Verify destination
        if not os.path.isdir(destination):
            try:
                os.makedirs(destination, exist_ok=True)
            except OSError as e:
                raise DownloadError(
                    f"Cannot access the download folder:\n{destination}",
                    str(e),
                ) from e

        # Build yt-dlp options
        format_selector = self._format_service.get_format_selector(
            quality, mode, output_format
        )
        postprocessors = self._format_service.get_postprocessors(mode, output_format)
        merge_format = self._format_service.get_merge_output_format(mode, output_format)

        output_template = os.path.join(destination, "%(title).80s.%(ext)s")

        ydl_opts = {
            "format": format_selector,
            "outtmpl": output_template,
            "trim_file_name": 120,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "progress_hooks": [self._make_progress_hook(progress_callback)],
            "postprocessor_hooks": [self._make_postprocessor_hook(progress_callback)],
            "noprogress": True,
        }

        # Audio metadata & artwork embedding
        if mode == DownloadMode.AUDIO_ONLY:
            ydl_opts["writethumbnail"] = True
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
            postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})

        # Subtitles
        if subtitles_lang and subtitles_lang != "none":
            from app.subtitles import SubtitleService
            sub_opts = SubtitleService().get_subtitle_options(subtitles_lang, embed=embed_subtitles)
            for k, v in sub_opts.items():
                if k == "postprocessors":
                    postprocessors.extend(v)
                else:
                    ydl_opts[k] = v

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        if merge_format:
            ydl_opts["merge_output_format"] = merge_format

        # Section clipping
        if clip_start or clip_end:
            from app.utils import parse_timestamp
            s_sec = parse_timestamp(clip_start) if clip_start else 0
            e_sec = parse_timestamp(clip_end) if clip_end else None
            if s_sec is not None and e_sec is not None and e_sec > s_sec:
                ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(s_sec, e_sec)])
                ydl_opts["force_keyframes_at_cuts"] = True
                logger.info("Configured clip range: %s to %s (%ds to %ds)", clip_start, clip_end, s_sec, e_sec)

        logger.info(
            "Starting download: url=%s quality=%s format=%s mode=%s dest=%s",
            url, quality, output_format, mode.value, destination,
        )
        logger.debug("Format selector: %s", format_selector)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self._current_process = ydl
                info = ydl.extract_info(url, download=True)
                self._current_process = None

            if self._cancel_event.is_set():
                raise DownloadCancelled()

            # Determine the final filename
            if info:
                filename = ydl.prepare_filename(info)
                # For audio extraction, extension changes
                if mode == DownloadMode.AUDIO_ONLY:
                    base = os.path.splitext(filename)[0]
                    ext_map = {"MP3": ".mp3", "M4A": ".m4a", "Opus": ".opus"}
                    filename = base + ext_map.get(output_format, ".mp3")
                elif merge_format:
                    base = os.path.splitext(filename)[0]
                    filename = base + "." + merge_format

                logger.info("Download complete: %s", filename)
                return filename

            return destination

        except DownloadCancelled:
            logger.info("Download cancelled by user.")
            raise

        except yt_dlp.utils.DownloadError as e:
            error_str = str(e).lower()
            if self._cancel_event.is_set():
                raise DownloadCancelled() from e

            user_msg = self._classify_download_error(error_str)
            logger.error("Download failed for %s: %s", url, e)
            raise DownloadError(user_msg, str(e)) from e

        except Exception as e:
            if self._cancel_event.is_set():
                raise DownloadCancelled() from e

            logger.error("Unexpected download error for %s: %s", url, e)
            raise DownloadError(
                "An unexpected error occurred during download.",
                str(e),
            ) from e

        finally:
            self._current_process = None

    def cancel(self) -> None:
        """Cancel the current download."""
        logger.info("Cancel requested.")
        self._cancel_event.set()

    def _make_progress_hook(
        self, callback: Callable[[DownloadProgress], None]
    ) -> Callable:
        """Create a yt-dlp progress hook that dispatches to callback."""

        def hook(data: dict) -> None:
            if self._cancel_event.is_set():
                raise DownloadCancelled()

            status = data.get("status", "")

            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes", 0)

                if total and total > 0:
                    percentage = (downloaded / total) * 100.0
                else:
                    percentage = 0.0

                progress = DownloadProgress(
                    status="downloading",
                    percentage=percentage,
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                    filename=data.get("filename"),
                )
                callback(progress)

            elif status == "finished":
                progress = DownloadProgress(
                    status="processing",
                    percentage=100.0,
                    downloaded_bytes=data.get("downloaded_bytes", 0),
                    total_bytes=data.get("total_bytes"),
                    filename=data.get("filename"),
                )
                callback(progress)

        return hook

    def _make_postprocessor_hook(
        self, callback: Callable[[DownloadProgress], None]
    ) -> Callable:
        """Create a yt-dlp postprocessor hook with descriptive step messages."""

        def hook(data: dict) -> None:
            if self._cancel_event.is_set():
                raise DownloadCancelled()

            status = data.get("status", "")
            pp_name = str(data.get("postprocessor", ""))

            if "Merger" in pp_name:
                desc = "Merging video and audio streams…"
            elif "ExtractAudio" in pp_name:
                desc = "Converting audio…"
            elif "EmbedSubtitle" in pp_name:
                desc = "Embedding subtitles…"
            elif "Metadata" in pp_name or "Thumbnail" in pp_name:
                desc = "Embedding metadata and artwork…"
            else:
                desc = "Processing and finalizing…"

            if status == "started":
                progress = DownloadProgress(
                    status="processing",
                    percentage=100.0,
                    step_description=desc,
                )
                callback(progress)

            elif status == "finished":
                progress = DownloadProgress(
                    status="finished",
                    percentage=100.0,
                    step_description="Finalizing output…",
                )
                callback(progress)

        return hook

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        return shutil.which("ffmpeg") is not None

    def _classify_download_error(self, error_msg: str) -> str:
        """Convert download error to user-friendly message."""
        if "permission" in error_msg:
            return (
                "Permission denied.\n"
                "Cannot write to the download folder."
            )
        if "file name too long" in error_msg or "errno 36" in error_msg:
            return (
                "File name too long for storage filesystem.\n"
                "The video title has been shortened to fit disk limits."
            )
        if "disk" in error_msg or "space" in error_msg or "no space" in error_msg:
            return (
                "Not enough disk space.\n"
                "Free up space and try again."
            )
        if "network" in error_msg or "connection" in error_msg:
            return (
                "Network error during download.\n"
                "Check your internet connection and try again."
            )
        if "format" in error_msg and "not available" in error_msg:
            return (
                "The selected format is not available.\n"
                "Try a different quality or format."
            )
        if "merge" in error_msg or "ffmpeg" in error_msg:
            return (
                "Error merging video and audio.\n"
                "Make sure FFmpeg is properly installed."
            )
        return (
            "Download failed.\n"
            "Please try again or try a different format."
        )
