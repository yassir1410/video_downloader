"""Download Queue UI view for monitoring and managing queued downloads."""

import logging
import os
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gtk, Pango

from app.models import DownloadStatus, DownloadTask
from app.queue import DownloadQueue
from app.utils import (
    format_eta,
    format_file_size,
    format_speed,
    open_file,
    open_folder,
)

logger = logging.getLogger(__name__)


class TaskRow(Gtk.ListBoxRow):
    """A list row displaying a single download task with actions and progress."""

    def __init__(self, task: DownloadTask, queue: DownloadQueue):
        super().__init__()
        self.task_id = task.id
        self._queue = queue

        self.set_activatable(False)
        self.set_selectable(False)

        self._build_ui(task)
        self.update(task)

    def _build_ui(self, task: DownloadTask) -> None:
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_top=10,
            margin_bottom=10,
        )

        # ── Header: Icon, Title, Buttons ────────────────────────────────────
        header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            valign=Gtk.Align.CENTER,
        )

        self._status_icon = Gtk.Image(
            icon_name="folder-download-symbolic",
            pixel_size=16,
        )
        header_box.append(self._status_icon)

        self._title_label = Gtk.Label(
            label=task.title or "Downloading video…",
            xalign=0,
            hexpand=True,
            ellipsize=Pango.EllipsizeMode.END,
            max_width_chars=32,
            css_classes=["heading"],
        )
        header_box.append(self._title_label)

        # Action buttons container
        self._btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            valign=Gtk.Align.CENTER,
        )
        header_box.append(self._btn_box)

        main_box.append(header_box)

        # ── Progress Bar ─────────────────────────────────────────────────────
        self._progress_bar = Gtk.ProgressBar(
            show_text=False,
            margin_top=2,
            margin_bottom=2,
        )
        main_box.append(self._progress_bar)

        # ── Subtitle / Details Label ─────────────────────────────────────────
        self._detail_label = Gtk.Label(
            label="",
            xalign=0,
            css_classes=["dim-label", "caption"],
            ellipsize=Pango.EllipsizeMode.END,
        )
        main_box.append(self._detail_label)

        self.set_child(main_box)

    def update(self, task: DownloadTask) -> None:
        """Update row widgets based on task's current status and progress."""
        self._title_label.set_label(task.title or "Video")

        # Clear existing action buttons
        while (child := self._btn_box.get_first_child()) is not None:
            self._btn_box.remove(child)

        status = task.status

        if status == DownloadStatus.WAITING:
            self._status_icon.set_from_icon_name("alarm-symbolic")
            self._progress_bar.set_visible(False)
            self._detail_label.set_label(f"Queued · {task.quality} {task.output_format}")

            # Cancel button
            btn_cancel = Gtk.Button(
                icon_name="window-close-symbolic",
                tooltip_text="Cancel",
                css_classes=["flat", "circular"],
            )
            btn_cancel.connect("clicked", lambda *_: self._queue.cancel_task(task.id))
            self._btn_box.append(btn_cancel)

        elif status == DownloadStatus.DOWNLOADING:
            self._status_icon.set_from_icon_name("folder-download-symbolic")
            self._progress_bar.set_visible(True)
            fraction = max(0.0, min(1.0, task.progress / 100.0))
            self._progress_bar.set_fraction(fraction)

            parts = [f"{task.progress:.0f}%"]
            if task.total_bytes and task.downloaded_bytes:
                parts.append(
                    f"{format_file_size(task.downloaded_bytes)} / {format_file_size(task.total_bytes)}"
                )
            elif task.downloaded_bytes:
                parts.append(format_file_size(task.downloaded_bytes))

            if task.speed:
                parts.append(format_speed(task.speed))
            if task.eta:
                parts.append(format_eta(task.eta))

            self._detail_label.set_label(" • ".join(parts))

            # Stop / Cancel button
            btn_stop = Gtk.Button(
                icon_name="process-stop-symbolic",
                tooltip_text="Cancel download",
                css_classes=["flat", "destructive-action", "circular"],
            )
            btn_stop.connect("clicked", lambda *_: self._queue.cancel_task(task.id))
            self._btn_box.append(btn_stop)

        elif status == DownloadStatus.PROCESSING:
            self._status_icon.set_from_icon_name("emblem-synchronizing-symbolic")
            self._progress_bar.set_visible(True)
            self._progress_bar.set_fraction(1.0)
            self._detail_label.set_label(task.processing_step or "Finalizing video…")

            # Cancel button
            btn_stop = Gtk.Button(
                icon_name="process-stop-symbolic",
                tooltip_text="Cancel",
                css_classes=["flat", "destructive-action", "circular"],
            )
            btn_stop.connect("clicked", lambda *_: self._queue.cancel_task(task.id))
            self._btn_box.append(btn_stop)

        elif status == DownloadStatus.COMPLETED:
            self._status_icon.set_from_icon_name("emblem-ok-symbolic")
            self._progress_bar.set_visible(False)
            self._detail_label.set_label("Completed")

            # Open File button
            if task.filepath and os.path.exists(task.filepath):
                btn_open_file = Gtk.Button(
                    icon_name="document-open-symbolic",
                    tooltip_text="Open file",
                    css_classes=["flat", "circular"],
                )
                btn_open_file.connect("clicked", lambda *_: open_file(task.filepath))
                self._btn_box.append(btn_open_file)

            # Open Folder button
            folder = os.path.dirname(task.filepath) if task.filepath else task.destination
            if folder and os.path.exists(folder):
                btn_open_folder = Gtk.Button(
                    icon_name="folder-symbolic",
                    tooltip_text="Open folder",
                    css_classes=["flat", "circular"],
                )
                btn_open_folder.connect("clicked", lambda *_: open_folder(folder))
                self._btn_box.append(btn_open_folder)

            # Delete / Remove from list
            btn_del = Gtk.Button(
                icon_name="edit-clear-symbolic",
                tooltip_text="Dismiss",
                css_classes=["flat", "circular"],
            )
            btn_del.connect("clicked", lambda *_: self._queue.remove_task(task.id))
            self._btn_box.append(btn_del)

        elif status == DownloadStatus.FAILED:
            self._status_icon.set_from_icon_name("dialog-error-symbolic")
            self._progress_bar.set_visible(False)
            err = task.error_message or "Download failed"
            self._detail_label.set_label(f"Failed: {err}")

            # Retry button
            btn_retry = Gtk.Button(
                icon_name="view-refresh-symbolic",
                tooltip_text="Retry",
                css_classes=["flat", "circular"],
            )
            btn_retry.connect("clicked", lambda *_: self._queue.retry_task(task.id))
            self._btn_box.append(btn_retry)

            # Remove button
            btn_del = Gtk.Button(
                icon_name="window-close-symbolic",
                tooltip_text="Dismiss",
                css_classes=["flat", "circular"],
            )
            btn_del.connect("clicked", lambda *_: self._queue.remove_task(task.id))
            self._btn_box.append(btn_del)

        elif status == DownloadStatus.CANCELLED:
            self._status_icon.set_from_icon_name("window-close-symbolic")
            self._progress_bar.set_visible(False)
            self._detail_label.set_label("Cancelled")

            # Retry button
            btn_retry = Gtk.Button(
                icon_name="view-refresh-symbolic",
                tooltip_text="Restart",
                css_classes=["flat", "circular"],
            )
            btn_retry.connect("clicked", lambda *_: self._queue.retry_task(task.id))
            self._btn_box.append(btn_retry)

            # Remove button
            btn_del = Gtk.Button(
                icon_name="edit-clear-symbolic",
                tooltip_text="Dismiss",
                css_classes=["flat", "circular"],
            )
            btn_del.connect("clicked", lambda *_: self._queue.remove_task(task.id))
            self._btn_box.append(btn_del)


class QueueView(Gtk.Box):
    """PreferencesGroup-like container displaying queued, active, and completed downloads."""

    def __init__(self, queue: DownloadQueue):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )

        self._queue = queue
        self._rows: dict[str, TaskRow] = {}

        self._build_ui()
        self._wire_queue_callbacks()

    def _build_ui(self) -> None:
        # Header Box: Title + "Clear Finished"
        header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_bottom=4,
        )

        title_label = Gtk.Label(
            label="Downloads",
            xalign=0,
            hexpand=True,
            css_classes=["heading"],
        )
        header_box.append(title_label)

        self._clear_btn = Gtk.Button(
            label="Clear Finished",
            css_classes=["flat", "caption"],
        )
        self._clear_btn.connect("clicked", lambda *_: self._queue.clear_completed())
        header_box.append(self._clear_btn)

        self.append(header_box)

        # List box for task rows
        self._list_box = Gtk.ListBox(
            css_classes=["boxed-list"],
            selection_mode=Gtk.SelectionMode.NONE,
        )
        self.append(self._list_box)

        # Initial visibility: hidden when empty
        self.set_visible(False)

    def _wire_queue_callbacks(self) -> None:
        self._queue.on_task_added = self._on_task_added
        self._queue.on_task_updated = self._on_task_updated
        self._queue.on_task_completed = self._on_task_completed
        self._queue.on_task_failed = self._on_task_failed
        self._queue.on_task_removed = self._on_task_removed

    def _on_task_added(self, task: DownloadTask) -> None:
        if task.id in self._rows:
            self._rows[task.id].update(task)
            return

        row = TaskRow(task, self._queue)
        self._rows[task.id] = row
        self._list_box.append(row)
        self.set_visible(True)

    def _on_task_updated(self, task: DownloadTask) -> None:
        if task.id in self._rows:
            self._rows[task.id].update(task)
        else:
            self._on_task_added(task)

    def _on_task_completed(self, task: DownloadTask) -> None:
        if task.id in self._rows:
            self._rows[task.id].update(task)

    def _on_task_failed(self, task: DownloadTask, error: str) -> None:
        if task.id in self._rows:
            self._rows[task.id].update(task)

    def _on_task_removed(self, task_id: str) -> None:
        if task_id in self._rows:
            row = self._rows.pop(task_id)
            self._list_box.remove(row)

        if not self._rows:
            self.set_visible(False)
