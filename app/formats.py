import logging
from typing import Optional

from app.models import DownloadMode, SmartRecommendation, VideoMetadata

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
            vcodec = fmt.get("vcodec")
            if vcodec == "none":
                continue

            height = fmt.get("height")
            if not height or not isinstance(height, int) or height <= 0:
                # Try resolution string e.g. "1280x720"
                res = fmt.get("resolution")
                if res and isinstance(res, str) and "x" in res:
                    try:
                        height = int(res.split("x")[1])
                    except (ValueError, IndexError):
                        height = None

            # Try format_note / format_id (e.g. "hd", "sd")
            if not height:
                note = str(fmt.get("format_note") or fmt.get("format_id") or "").lower()
                if "1080" in note:
                    height = 1080
                elif "720" in note or "hd" in note:
                    height = 720
                elif "480" in note or "sd" in note:
                    height = 480
                elif "360" in note:
                    height = 360

            if height and isinstance(height, int) and height > 0:
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
        if quality in ("Best", "Best Available"):
            return None
        # Extract digits before 'p'
        try:
            return int(quality.split("p")[0])
        except (ValueError, IndexError):
            return None

    def calculate_estimated_size(
        self,
        metadata: VideoMetadata,
        quality: str,
        output_format: str = "MP4",
        mode: DownloadMode = DownloadMode.VIDEO_AUDIO,
    ) -> Optional[int]:
        """Estimate the file size for a given quality and mode in bytes.

        Uses filesize, filesize_approx, or tbr/abr * duration if available.
        For separate video+audio streams, sums both streams.
        Returns None if size cannot be determined reliably.
        """
        raw_formats = metadata.raw_formats
        if not raw_formats:
            return None

        duration = metadata.duration

        if mode == DownloadMode.AUDIO_ONLY:
            audio_formats = [
                f for f in raw_formats
                if f.get("vcodec") == "none" and f.get("acodec") and f.get("acodec") != "none"
            ]
            if not audio_formats:
                audio_formats = [
                    f for f in raw_formats
                    if f.get("acodec") and f.get("acodec") != "none"
                ]

            if not audio_formats:
                return None

            max_size = 0
            for af in audio_formats:
                sz = af.get("filesize") or af.get("filesize_approx")
                if sz and sz > max_size:
                    max_size = sz
                elif not sz and af.get("abr") and duration:
                    approx = int(af["abr"] * 1000 / 8 * duration)
                    if approx > max_size:
                        max_size = approx
            return max_size if max_size > 0 else None

        # Mode is VIDEO_AUDIO
        height = self._parse_height(quality)

        video_candidates = []
        for f in raw_formats:
            if f.get("vcodec") == "none":
                continue
            h = f.get("height")
            if not h and f.get("resolution") and "x" in str(f.get("resolution")):
                try:
                    h = int(str(f["resolution"]).split("x")[1])
                except (ValueError, IndexError):
                    h = None

            if height is None:
                video_candidates.append(f)
            elif h is not None and abs(h - height) <= height * 0.15:
                video_candidates.append(f)

        if not video_candidates:
            video_candidates = [f for f in raw_formats if f.get("vcodec") != "none"]

        if not video_candidates:
            return None

        ext = output_format.lower()
        matching_ext = [f for f in video_candidates if f.get("ext") == ext]
        pool = matching_ext if matching_ext else video_candidates

        def video_sort_key(f):
            sz = f.get("filesize") or f.get("filesize_approx") or 0
            if not sz and f.get("tbr") and duration:
                sz = int(f["tbr"] * 1000 / 8 * duration)
            return (f.get("height") or 0, sz)

        best_video = max(pool, key=video_sort_key)
        v_size = best_video.get("filesize") or best_video.get("filesize_approx")
        if not v_size and best_video.get("tbr") and duration:
            v_size = int(best_video["tbr"] * 1000 / 8 * duration)

        if not v_size:
            return None

        has_audio = best_video.get("acodec") and best_video.get("acodec") != "none"
        if has_audio:
            return v_size

        audio_formats = [
            f for f in raw_formats
            if f.get("vcodec") == "none" and f.get("acodec") and f.get("acodec") != "none"
        ]
        a_size = 0
        if audio_formats:
            def audio_sort_key(f):
                sz = f.get("filesize") or f.get("filesize_approx") or 0
                if not sz and f.get("abr") and duration:
                    sz = int(f["abr"] * 1000 / 8 * duration)
                return sz

            best_audio = max(audio_formats, key=audio_sort_key)
            a_size = best_audio.get("filesize") or best_audio.get("filesize_approx") or 0
            if not a_size and best_audio.get("abr") and duration:
                a_size = int(best_audio["abr"] * 1000 / 8 * duration)

        return v_size + a_size

    def get_smart_recommendation(self, metadata: VideoMetadata) -> SmartRecommendation:
        """Determine the recommended download configuration.

        Prioritizes:
        1. 1080p MP4 if available
        2. 720p MP4 if available
        3. Best available resolution MP4 / best
        """
        qualities = self.get_available_qualities(metadata)

        target_q = "Best"
        if "1080p" in qualities:
            target_q = "1080p"
        elif "720p" in qualities:
            target_q = "720p"
        elif len(qualities) > 1:
            target_q = qualities[1]
        else:
            target_q = "Best"

        rec_format = "MP4"
        rec_mode = DownloadMode.VIDEO_AUDIO

        est_size = self.calculate_estimated_size(metadata, target_q, rec_format, rec_mode)

        if est_size and est_size > 0:
            from app.utils import format_file_size
            label = f"{target_q} · {rec_format} · ~{format_file_size(est_size)}"
        else:
            label = f"{target_q} · {rec_format}"

        return SmartRecommendation(
            quality=target_q,
            format=rec_format,
            mode=rec_mode,
            estimated_size=est_size,
            label=label,
        )

    def get_available_qualities_with_details(
        self,
        metadata: VideoMetadata,
        mode: DownloadMode = DownloadMode.VIDEO_AUDIO,
        output_format: str = "MP4",
    ) -> list[tuple[str, str]]:
        """Return list of (quality_code, detailed_label_with_size)."""
        from app.utils import format_file_size
        qualities = self.get_available_qualities(metadata)
        results = []
        for q in qualities:
            sz = self.calculate_estimated_size(metadata, q, output_format, mode)
            if sz and sz > 0:
                display = f"{q} (~{format_file_size(sz)})"
            else:
                display = q
            results.append((q, display))
        return results
