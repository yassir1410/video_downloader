import logging
import os
import subprocess
from typing import Optional
from urllib.parse import urlparse

from app.models import VideoProvider

logger = logging.getLogger(__name__)


def format_duration(seconds: Optional[int]) -> str:
    """Convert seconds to human-readable duration.
    
    Examples:
        None -> "Unknown duration"
        0 -> "0:00"
        59 -> "0:59"
        872 -> "14:32"
        5058 -> "1:24:18"
    """
    if seconds is None:
        return "Unknown duration"
    if seconds < 0:
        seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable file size (binary, 1024-based).
    
    Examples:
        0 -> "0 B"
        1024 -> "1.0 KB"
        1048576 -> "1.0 MB"
        125829120 -> "120.0 MB"
        1073741824 -> "1.0 GB"
    """
    if size_bytes < 0:
        size_bytes = 0
    if size_bytes == 0:
        return "0 B"
    units = [("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)]
    for unit, threshold in units:
        if size_bytes >= threshold:
            return f"{size_bytes / threshold:.1f} {unit}"
    return f"{size_bytes} B"


def format_speed(bytes_per_sec: float) -> str:
    """Convert bytes/sec to human-readable download speed.
    
    Examples:
        0 -> "0 B/s"
        1024 -> "1.0 KB/s"
        8500000 -> "8.1 MB/s"
    """
    if bytes_per_sec <= 0:
        return "0 B/s"
    units = [("GB/s", 1024**3), ("MB/s", 1024**2), ("KB/s", 1024)]
    for unit, threshold in units:
        if bytes_per_sec >= threshold:
            return f"{bytes_per_sec / threshold:.1f} {unit}"
    return f"{bytes_per_sec:.0f} B/s"


def format_eta(seconds: int) -> str:
    """Convert seconds to human-readable ETA string.
    
    Examples:
        0 -> "0 sec remaining"
        14 -> "14 sec remaining"
        60 -> "1 min remaining"
        125 -> "2 min 5 sec remaining"
        3661 -> "1 hr 1 min remaining"
    """
    if seconds < 0:
        seconds = 0
    if seconds == 0:
        return "0 sec remaining"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hr")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if secs > 0 and hours == 0:  # Don't show seconds for hour+ durations
        parts.append(f"{secs} sec")
    
    return " ".join(parts) + " remaining"


def is_valid_url(text: str) -> bool:
    """Check if text looks like a valid HTTP/HTTPS URL."""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    return text.startswith("http://") or text.startswith("https://")


def detect_provider(url: str) -> VideoProvider:
    """Detect the video provider from a URL.

    Recognizes YouTube and Facebook domains and URL structures.
    Any other valid URL returns VideoProvider.OTHER.
    """
    if not url or not isinstance(url, str):
        return VideoProvider.OTHER

    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or "").lower()
        if ":" in host:
            host = host.split(":")[0]
    except Exception:
        return VideoProvider.OTHER

    # YouTube checks
    youtube_domains = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "gaming.youtube.com",
        "youtu.be",
    }
    if host in youtube_domains or host.endswith(".youtube.com") or host == "youtu.be":
        return VideoProvider.YOUTUBE

    # Facebook checks
    facebook_domains = {
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "web.facebook.com",
        "touch.facebook.com",
        "fb.watch",
        "fb.com",
    }
    if (
        host in facebook_domains
        or host.endswith(".facebook.com")
        or host.endswith(".fb.watch")
        or host == "fb.watch"
    ):
        return VideoProvider.FACEBOOK

    return VideoProvider.OTHER


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available on the system."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def open_folder(path: str) -> None:
    """Open a folder in the system file manager using Gio."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio

        uri = Gio.File.new_for_path(path).get_uri()
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except Exception as e:
        logger.error("Failed to open folder %s: %s", path, e)


def open_file(filepath: str) -> None:
    """Open a file with the system default application using Gio."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio

        uri = Gio.File.new_for_path(filepath).get_uri()
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except Exception as e:
        logger.error("Failed to open file %s: %s", filepath, e)


def parse_timestamp(text: str) -> Optional[int]:
    """Parse timestamp string (HH:MM:SS, MM:SS, or seconds) into integer seconds.

    Examples:
        "01:23:45" -> 5025
        "05:30" -> 330
        "90" -> 90
        "" -> None
        "invalid" -> None
    """
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None

    parts = text.split(":")
    try:
        if len(parts) == 3:
            h, m, s = map(int, parts)
            if h < 0 or m < 0 or m >= 60 or s < 0 or s >= 60:
                return None
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(int, parts)
            if m < 0 or s < 0 or s >= 60:
                return None
            return m * 60 + s
        elif len(parts) == 1:
            val = int(parts[0])
            return val if val >= 0 else None
    except ValueError:
        return None
    return None


def format_timestamp(seconds: int) -> str:
    """Format total seconds into HH:MM:SS."""
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def check_disk_space(path: str, required_bytes: int) -> tuple[bool, int, int]:
    """Check if destination directory has enough free disk space.

    Returns:
        (has_enough_space, free_bytes, required_bytes)
    """
    import shutil
    try:
        check_dir = path if os.path.isdir(path) else os.path.dirname(path)
        if not check_dir or not os.path.exists(check_dir):
            check_dir = os.path.expanduser("~")
        usage = shutil.disk_usage(check_dir)
        free_bytes = usage.free
        has_enough = free_bytes >= required_bytes
        return (has_enough, free_bytes, required_bytes)
    except Exception as e:
        logger.warning("Could not check disk space for %s: %s", path, e)
        return (True, 0, required_bytes)


def extract_urls(text: str) -> list[str]:
    """Extract valid HTTP/HTTPS URLs from multi-line or whitespace-separated text."""
    if not text or not isinstance(text, str):
        return []

    tokens = text.split()
    urls = []
    seen = set()
    for token in tokens:
        # Strip trailing punctuation often attached to pasted text
        clean = token.strip(" \t\n\r<>()[]{}\"',.;!?")
        if is_valid_url(clean) and clean not in seen:
            seen.add(clean)
            urls.append(clean)
    return urls
