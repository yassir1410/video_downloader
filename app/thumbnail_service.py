"""Thumbnail and video frame extraction service for visual clipping."""

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gdk, GLib

from app.models import VideoMetadata

logger = logging.getLogger(__name__)

CACHE_BASE_DIR = os.path.expanduser("~/.cache/video-downloader/thumbnails")


class ThumbnailService:
    """Extracts and caches video frames and filmstrip thumbnails asynchronously."""

    def __init__(self, cache_dir: str = CACHE_BASE_DIR):
        self._cache_dir = cache_dir
        os.makedirs(self._cache_dir, exist_ok=True)

        self._mem_cache: dict[str, Gdk.Texture] = {}
        self._lock = threading.Lock()

        # Single-worker queue for debounced frame preview extraction
        self._preview_lock = threading.Lock()
        self._preview_event = threading.Event()
        self._pending_preview: Optional[tuple[VideoMetadata, float, Callable[[float, Optional[Gdk.Texture]], None]]] = None
        self._running = True

        self._preview_thread = threading.Thread(
            target=self._preview_worker_loop,
            daemon=True,
            name="ThumbnailPreviewWorker",
        )
        self._preview_thread.start()

    def get_stream_url(self, metadata: VideoMetadata) -> Optional[tuple[str, dict]]:
        """Find the most lightweight video stream URL and headers for frame extraction."""
        if not metadata or not metadata.raw_formats:
            return None

        formats = metadata.raw_formats
        candidates = []

        for f in formats:
            url = f.get("url")
            if not url:
                continue

            # Skip audio-only streams
            vcodec = f.get("vcodec", "")
            if vcodec == "none":
                continue

            height = f.get("height") or 0
            tbr = f.get("tbr") or 0
            filesize = f.get("filesize") or f.get("filesize_approx") or 0
            protocol = f.get("protocol", "")

            # Avoid mhtml/storyboard formats here; we want direct media stream
            if "mhtml" in protocol or "storyboard" in f.get("format_id", ""):
                continue

            candidates.append({
                "url": url,
                "height": height,
                "tbr": tbr,
                "filesize": filesize,
                "headers": f.get("http_headers") or {},
            })

        if not candidates:
            return None

        # Prioritize 240p to 360p (fastest range-seek with good quality for thumbnails)
        # If not present, sort by lowest height > 0
        def score(c):
            h = c["height"]
            if h in (240, 360):
                return (0, h)
            elif h in (144, 480):
                return (1, h)
            elif h > 0:
                return (2, h)
            return (3, c["tbr"] or 9999)

        candidates.sort(key=score)
        best = candidates[0]
        return best["url"], best["headers"]

    def _get_cache_path(self, url: str, timestamp: float, prefix: str = "frame") -> str:
        """Compute disk cache path for a given URL and timestamp."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        folder = os.path.join(self._cache_dir, url_hash)
        os.makedirs(folder, exist_ok=True)
        # Round timestamp to 2 decimal places to enable cache reuse
        sec_int = int(round(timestamp, 2) * 100)
        return os.path.join(folder, f"{prefix}_{sec_int:08d}.jpg")

    def extract_frame_sync(
        self,
        stream_url: str,
        timestamp: float,
        headers: Optional[dict] = None,
        width: int = 180,
    ) -> Optional[str]:
        """Extract a single frame to disk at timestamp using FFmpeg range seeking."""
        cache_path = self._get_cache_path(stream_url, timestamp)
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            return cache_path

        cmd = ["ffmpeg", "-y", "-loglevel", "error"]

        if headers:
            header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            cmd.extend(["-headers", header_str])

        cmd.extend([
            "-ss", f"{max(0.0, timestamp):.3f}",
            "-i", stream_url,
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            "-f", "image2",
            cache_path,
        ])

        try:
            res = subprocess.run(cmd, capture_output=True, timeout=6)
            if res.returncode == 0 and os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
                return cache_path
            else:
                logger.debug("FFmpeg frame extraction exited with code %s: %s", res.returncode, res.stderr.decode("utf-8", "ignore"))
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug("FFmpeg frame extraction failed for t=%.2f: %s", timestamp, e)

        return None

    def request_frame_preview(
        self,
        metadata: VideoMetadata,
        timestamp: float,
        callback: Callable[[float, Optional[Gdk.Texture]], None],
    ) -> None:
        """Request a frame preview at timestamp (debounced, non-blocking)."""
        cache_key = f"{metadata.webpage_url}:{int(round(timestamp, 1) * 10)}"
        with self._lock:
            if cache_key in self._mem_cache:
                texture = self._mem_cache[cache_key]
                GLib.idle_add(callback, timestamp, texture)
                return

        with self._preview_lock:
            self._pending_preview = (metadata, timestamp, callback)
            self._preview_event.set()

    def _preview_worker_loop(self) -> None:
        """Worker loop processing the latest requested frame preview."""
        while self._running:
            self._preview_event.wait(timeout=1.0)
            self._preview_event.clear()

            with self._preview_lock:
                req = self._pending_preview
                self._pending_preview = None

            if not req:
                continue

            metadata, timestamp, callback = req
            stream_info = self.get_stream_url(metadata)
            if not stream_info:
                GLib.idle_add(callback, timestamp, None)
                continue

            stream_url, headers = stream_info
            path = self.extract_frame_sync(stream_url, timestamp, headers=headers, width=280)

            texture = None
            if path and os.path.exists(path):
                try:
                    texture = Gdk.Texture.new_from_filename(path)
                    cache_key = f"{metadata.webpage_url}:{int(round(timestamp, 1) * 10)}"
                    with self._lock:
                        self._mem_cache[cache_key] = texture
                except Exception as e:
                    logger.debug("Could not load texture from %s: %s", path, e)

            GLib.idle_add(callback, timestamp, texture)

    def generate_filmstrip(
        self,
        metadata: VideoMetadata,
        count: int = 8,
        on_thumbnail_ready: Optional[Callable[[int, float, Gdk.Texture], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        """Generate a series of filmstrip thumbnails asynchronously across duration."""
        if not metadata or not metadata.duration or metadata.duration <= 0:
            if on_finished:
                GLib.idle_add(on_finished)
            return

        def worker():
            stream_info = self.get_stream_url(metadata)
            if not stream_info:
                if on_finished:
                    GLib.idle_add(on_finished)
                return

            stream_url, headers = stream_info
            duration = float(metadata.duration)
            interval = duration / count

            for i in range(count):
                t = min(duration, max(0.0, (i + 0.5) * interval))
                path = self.extract_frame_sync(stream_url, t, headers=headers, width=120)
                if path and os.path.exists(path):
                    try:
                        texture = Gdk.Texture.new_from_filename(path)
                        if on_thumbnail_ready:
                            GLib.idle_add(on_thumbnail_ready, i, t, texture)
                    except Exception as e:
                        logger.debug("Failed to create filmstrip texture %s: %s", i, e)

            if on_finished:
                GLib.idle_add(on_finished)

        threading.Thread(target=worker, daemon=True, name="FilmstripWorker").start()

    def clear_cache(self) -> None:
        """Clear cached thumbnails."""
        with self._lock:
            self._mem_cache.clear()
        try:
            if os.path.exists(self._cache_dir):
                shutil.rmtree(self._cache_dir)
                os.makedirs(self._cache_dir, exist_ok=True)
        except Exception as e:
            logger.warning("Error clearing thumbnail cache: %s", e)
