import logging
import subprocess

logger = logging.getLogger(__name__)


def format_duration(seconds: int) -> str:
    """Convert seconds to human-readable duration.
    
    Examples:
        0 -> "0:00"
        59 -> "0:59"
        872 -> "14:32"
        5058 -> "1:24:18"
    """
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
