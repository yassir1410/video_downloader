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


class VideoProvider(Enum):
    YOUTUBE = "YouTube"
    FACEBOOK = "Facebook"
    OTHER = "Other"


class DownloadStatus(Enum):
    WAITING = "waiting"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    uploader: Optional[str] = None
    duration: Optional[int] = None  # seconds
    thumbnail_url: Optional[str] = None
    webpage_url: str = ""
    raw_formats: list = field(default_factory=list)
    provider: VideoProvider = VideoProvider.OTHER
    subtitles: dict = field(default_factory=dict)
    automatic_captions: dict = field(default_factory=dict)


@dataclass
class SmartRecommendation:
    quality: str
    format: str
    mode: DownloadMode
    estimated_size: Optional[int]
    label: str  # e.g., "1080p · MP4 · ~124 MB"


@dataclass
class DownloadProgress:
    status: str  # "downloading", "finished", "error", "processing"
    percentage: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    speed: Optional[float] = None  # bytes/sec
    eta: Optional[int] = None  # seconds
    filename: Optional[str] = None
    step_description: Optional[str] = None


@dataclass
class DownloadTask:
    id: str
    url: str
    title: str
    uploader: Optional[str] = None
    thumbnail_url: Optional[str] = None
    quality: str = "Best"
    output_format: str = "MP4"
    mode: DownloadMode = DownloadMode.VIDEO_AUDIO
    destination: str = ""
    status: DownloadStatus = DownloadStatus.WAITING
    progress: float = 0.0
    speed: Optional[float] = None
    eta: Optional[int] = None
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    error_message: Optional[str] = None
    filepath: Optional[str] = None
    clip_start: Optional[str] = None
    clip_end: Optional[str] = None
    subtitles_lang: Optional[str] = None
    embed_subtitles: bool = False
    processing_step: Optional[str] = None


@dataclass
class HistoryItem:
    id: str
    title: str
    url: str
    provider: str
    date: str
    filepath: str
    output_format: str
    quality: str
    filesize: Optional[int] = None
