"""Format detection and selection service."""

import logging
from typing import Optional

from app.models import DownloadMode, VideoMetadata

logger = logging.getLogger(__name__)

# Standard resolution labels in descending order
STANDARD_RESOLUTIONS = [
    (2160, "2160p (4K)"),
    (1440, "1440p"),
    (1080, "1080p"),
    (720, "720p"),
    (480, "480p"),
    (360, "360p"),
    (240, "240p"),
    (144, "144p"),
]


class FormatService:
    """Handles format detection and yt-dlp format string generation."""

    def get_available_qualities(self, metadata: VideoMetadata) -> list[str]:
        """Extract unique available resolutions from metadata, sorted highest first.
        
        Always prepends 'Best' as the first option.
        
        Args:
            metadata: VideoMetadata with raw_formats from yt-dlp.
            
        Returns:
            List like ['Best', '1080p', '720p', '360p']
        """
        heights = set()
        for fmt in metadata.raw_formats:
            height = fmt.get("height")
            vcodec = fmt.get("vcodec", "none")
            # Only include formats that have actual video
            if height and isinstance(height, int) and height > 0 and vcodec != "none":
                heights.add(height)
        
        # Map to standard labels
        qualities = []
        for std_height, label in STANDARD_RESOLUTIONS:
            # Check if any available height matches this standard
            if std_height in heights:
                qualities.append(label)
            else:
                # Check if there's a close match (within 10%)
                for h in heights:
                    if abs(h - std_height) <= std_height * 0.1:
                        qualities.append(label)
                        break
        
        # Remove duplicates while preserving order
        seen = set()
        unique_qualities = []
        for q in qualities:
            if q not in seen:
                seen.add(q)
                unique_qualities.append(q)
        
        return ["Best"] + unique_qualities

    def get_output_formats(self, mode: DownloadMode) -> list[str]:
        """Return available output formats for the given download mode.
        
        Args:
            mode: DownloadMode.VIDEO_AUDIO or DownloadMode.AUDIO_ONLY
            
        Returns:
            List of format strings.
        """
        if mode == DownloadMode.VIDEO_AUDIO:
            return ["MP4", "WebM"]
        elif mode == DownloadMode.AUDIO_ONLY:
            return ["MP3", "M4A", "Opus"]
        return ["MP4"]

    def get_format_selector(self, quality: str, mode: DownloadMode, output_format: str) -> str:
        """Generate a yt-dlp format selector string.
        
        Args:
            quality: User-selected quality like 'Best', '1080p', '720p'
            mode: Download mode (Video+Audio or Audio Only)
            output_format: Desired output format ('MP4', 'WebM', 'MP3', etc.)
            
        Returns:
            yt-dlp format selector string.
        """
        if mode == DownloadMode.AUDIO_ONLY:
            return "bestaudio/best"
        
        # Extract height from quality label
        height = self._parse_height(quality)
        
        if height is None or quality == "Best":
            # Best quality
            if output_format == "MP4":
                return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            elif output_format == "WebM":
                return "bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best"
            return "bestvideo+bestaudio/best"
        
        # Specific resolution
        if output_format == "MP4":
            return (
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        elif output_format == "WebM":
            return (
                f"bestvideo[height<={height}][ext=webm]+bestaudio[ext=webm]/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"

    def get_postprocessors(self, mode: DownloadMode, output_format: str) -> list[dict]:
        """Generate yt-dlp postprocessor configuration.
        
        Args:
            mode: Download mode.
            output_format: Desired output format.
            
        Returns:
            List of postprocessor dicts for yt-dlp.
        """
        if mode == DownloadMode.AUDIO_ONLY:
            codec_map = {
                "MP3": ("mp3", "192"),
                "M4A": ("m4a", "192"),
                "Opus": ("opus", "128"),
            }
            codec, quality = codec_map.get(output_format, ("mp3", "192"))
            return [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": quality,
            }]
        return []

    def get_merge_output_format(self, mode: DownloadMode, output_format: str) -> Optional[str]:
        """Get the merge output format for yt-dlp.
        
        Args:
            mode: Download mode.
            output_format: Desired output format.
            
        Returns:
            Merge format string or None.
        """
        if mode == DownloadMode.VIDEO_AUDIO:
            return output_format.lower()  # "mp4" or "webm"
        return None

    def _parse_height(self, quality: str) -> Optional[int]:
        """Extract height value from quality label.
        
        Examples:
            '1080p' -> 1080
            '2160p (4K)' -> 2160
            'Best' -> None
        """
        if quality == "Best":
            return None
        # Extract digits before 'p'
        try:
            return int(quality.split("p")[0])
        except (ValueError, IndexError):
            return None
