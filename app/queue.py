"""Download queue service for sequential task management."""

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Callable, Optional

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from app.downloader import DownloadCancelled, DownloadError, DownloaderService
from app.history import HistoryService
from app.models import (
    DownloadMode,
    DownloadProgress,
    DownloadStatus,
    DownloadTask,
    HistoryItem,
)
from app.utils import detect_provider

logger = logging.getLogger(__name__)


class DownloadQueue:
    """Manages sequential execution of queued video download tasks."""

    def __init__(
        self,
        downloader_service: Optional[DownloaderService] = None,
        history_service: Optional[HistoryService] = None,
    ):
        self._downloader = downloader_service or DownloaderService()
        self._history = history_service or HistoryService()

        self._tasks: list[DownloadTask] = []
        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._current_task: Optional[DownloadTask] = None
        self._running = True

        # Callbacks (dispatched to GLib main thread)
        self.on_task_added: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_updated: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_completed: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_failed: Optional[Callable[[DownloadTask, str], None]] = None
        self.on_task_removed: Optional[Callable[[str], None]] = None

        # Start worker thread
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="DownloadQueueWorker",
        )
        self._worker_thread.start()

    def add_task(self, task: DownloadTask) -> str:
        """Add a new task to the queue."""
        if not task.id:
            task.id = str(uuid.uuid4())[:8]

        with self._lock:
            self._tasks.append(task)

        logger.info("Added task to queue: id=%s title=%s", task.id, task.title)
        self._dispatch(self.on_task_added, task)
        self._wake_event.set()
        return task.id

    def cancel_task(self, task_id: str) -> None:
        """Cancel a running or queued task."""
        with self._lock:
            for task in self._tasks:
                if task.id == task_id:
                    if task.status in (DownloadStatus.WAITING,):
                        task.status = DownloadStatus.CANCELLED
                        self._dispatch(self.on_task_updated, task)
                        return
                    elif task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING):
                        self._downloader.cancel()
                        return

    def retry_task(self, task_id: str) -> None:
        """Reset a failed or cancelled task back to WAITING."""
        with self._lock:
            for task in self._tasks:
                if task.id == task_id:
                    task.status = DownloadStatus.WAITING
                    task.progress = 0.0
                    task.speed = None
                    task.eta = None
                    task.error_message = None
                    task.processing_step = None
                    self._dispatch(self.on_task_updated, task)
                    self._wake_event.set()
                    return

    def remove_task(self, task_id: str) -> None:
        """Remove a task from the queue."""
        self.cancel_task(task_id)
        with self._lock:
            self._tasks = [t for t in self._tasks if t.id != task_id]
        self._dispatch(self.on_task_removed, task_id)

    def clear_completed(self) -> None:
        """Remove all completed, failed, or cancelled tasks."""
        with self._lock:
            retained = []
            removed_ids = []
            for t in self._tasks:
                if t.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED):
                    removed_ids.append(t.id)
                else:
                    retained.append(t)
            self._tasks = retained

        for tid in removed_ids:
            self._dispatch(self.on_task_removed, tid)

    def get_tasks(self) -> list[DownloadTask]:
        """Get copy of all tasks."""
        with self._lock:
            return list(self._tasks)

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Find a task by ID."""
        with self._lock:
            for t in self._tasks:
                if t.id == task_id:
                    return t
        return None

    def get_active_count(self) -> int:
        """Count tasks currently downloading or waiting."""
        with self._lock:
            return sum(
                1 for t in self._tasks
                if t.status in (DownloadStatus.WAITING, DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING)
            )

    # ─── Worker Loop ─────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        """Sequential background loop processing tasks."""
        while self._running:
            task = self._get_next_waiting_task()
            if not task:
                self._wake_event.wait(timeout=1.0)
                self._wake_event.clear()
                continue

            self._process_task(task)

    def _get_next_waiting_task(self) -> Optional[DownloadTask]:
        """Retrieve next task in WAITING state."""
        with self._lock:
            for task in self._tasks:
                if task.status == DownloadStatus.WAITING:
                    return task
        return None

    def _process_task(self, task: DownloadTask) -> None:
        """Execute a single download task."""
        self._current_task = task
        task.status = DownloadStatus.DOWNLOADING
        self._dispatch(self.on_task_updated, task)

        def progress_cb(prog: DownloadProgress):
            task.progress = prog.percentage
            task.downloaded_bytes = prog.downloaded_bytes
            task.total_bytes = prog.total_bytes
            task.speed = prog.speed
            task.eta = prog.eta

            if prog.status == "processing":
                task.status = DownloadStatus.PROCESSING
                task.processing_step = prog.step_description or "Merging and finalizing…"
            elif prog.status == "downloading":
                task.status = DownloadStatus.DOWNLOADING

            self._dispatch(self.on_task_updated, task)

        try:
            filepath = self._downloader.download(
                url=task.url,
                quality=task.quality,
                output_format=task.output_format,
                mode=task.mode,
                destination=task.destination,
                progress_callback=progress_cb,
                clip_start=task.clip_start,
                clip_end=task.clip_end,
                subtitles_lang=task.subtitles_lang,
                embed_subtitles=task.embed_subtitles,
            )
            task.status = DownloadStatus.COMPLETED
            task.progress = 100.0
            task.filepath = filepath
            task.processing_step = None
            self._dispatch(self.on_task_completed, task)

            # Record in history
            try:
                import os
                fsize = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else None
                provider = detect_provider(task.url).value
                item = HistoryItem(
                    id=task.id,
                    title=task.title,
                    url=task.url,
                    provider=provider,
                    date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    filepath=filepath or "",
                    output_format=task.output_format,
                    quality=task.quality,
                    filesize=fsize,
                )
                self._history.add_item(item)
            except Exception as e:
                logger.warning("Could not record history: %s", e)

        except DownloadCancelled:
            task.status = DownloadStatus.CANCELLED
            task.processing_step = None
            logger.info("Task %s cancelled", task.id)
            self._dispatch(self.on_task_updated, task)

        except DownloadError as e:
            task.status = DownloadStatus.FAILED
            task.error_message = e.user_message
            task.processing_step = None
            logger.error("Task %s failed: %s", task.id, e)
            self._dispatch(self.on_task_failed, task, e.user_message)

        except Exception as e:
            task.status = DownloadStatus.FAILED
            task.error_message = "An unexpected error occurred during download."
            task.processing_step = None
            logger.error("Task %s unexpected error: %s", task.id, e)
            self._dispatch(self.on_task_failed, task, str(e))

        finally:
            self._current_task = None

    def _dispatch(self, callback: Optional[Callable], *args) -> None:
        """Safely schedule a callback onto the GLib main loop."""
        if callback:
            def runner():
                try:
                    callback(*args)
                except Exception as e:
                    logger.error("Error in queue callback: %s", e)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(runner)
