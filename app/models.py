from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AppState(Enum):
    EMPTY = "empty"
    FETCHING_METADATA = "fetching"
    READY = "ready"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class DownloadMode(Enum):
    VIDEO_AUDIO = "Video + Audio"
    AUDIO_ONLY = "Audio Only"


@dataclass
class VideoFormat:
    format_id: str
    extension: str
    resolution: str  # e.g., "1080p", "720p"
    height: Optional[int] = None
    width: Optional[int] = None
    fps: Optional[float] = None
    filesize: Optional[int] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    has_video: bool = True
    has_audio: bool = True


@dataclass
class VideoMetadata:
    title: str
    uploader: str
    duration: int  # seconds
    thumbnail_url: str
    webpage_url: str
    raw_formats: list = field(default_factory=list)


@dataclass
class DownloadProgress:
    status: str  # "downloading", "finished", "error", "processing"
    percentage: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    speed: Optional[float] = None  # bytes/sec
    eta: Optional[int] = None  # seconds
    filename: Optional[str] = None
