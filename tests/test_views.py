"""Unit tests for UI views."""

import os
import unittest
from unittest.mock import MagicMock

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from app.history import HistoryService
from app.models import (
    DownloadMode,
    DownloadStatus,
    DownloadTask,
    HistoryItem,
    SmartRecommendation,
    VideoMetadata,
    VideoProvider,
)
from app.queue import DownloadQueue
from app.views.history_dialog import HistoryDialog, HistoryRow
from app.views.options_expander import OptionsExpanderView
from app.views.queue_view import QueueView, TaskRow
from app.views.smart_card import SmartCardView

# Ensure Adw is initialized for testing
app = Adw.Application(application_id="io.github.videodownloader.Tests")


class TestViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Trigger application startup/activation once
        cls.app = app

    def test_smart_card_view(self):
        """Test SmartCardView metadata and recommendation binding."""
        download_called = False

        def on_dl():
            nonlocal download_called
            download_called = True

        card = SmartCardView(on_download=on_dl)
        self.assertIsNotNone(card)

        metadata = VideoMetadata(
            title="Test Video Title",
            uploader="Test Channel",
            duration=365,
            thumbnail_url="http://example.com/thumb.jpg",
            webpage_url="https://youtube.com/watch?v=123",
            provider=VideoProvider.YOUTUBE,
        )
        rec = SmartRecommendation(
            quality="1080p",
            format="MP4",
            mode=DownloadMode.VIDEO_AUDIO,
            estimated_size=50_000_000,
            label="1080p · MP4 · ~50 MB",
        )

        card.set_metadata(metadata, rec)
        self.assertEqual(card._title_label.get_label(), "Test Video Title")
        self.assertEqual(card._channel_label.get_label(), "Test Channel")
        self.assertEqual(card._recommendation_label.get_label(), "1080p · MP4 · ~50 MB")
        self.assertIn("YOUTUBE", card._provider_badge.get_label())

        # Test download button callback
        card._download_button.emit("clicked")
        self.assertTrue(download_called)

        # Test options toggle
        card.set_options_expanded(True)
        self.assertTrue(card._options_toggle.get_active())

    def test_options_expander_view(self):
        """Test OptionsExpanderView setters, getters, and population."""
        opts = OptionsExpanderView(default_dir="/tmp/downloads")

        metadata = VideoMetadata(
            title="Sample Video",
            uploader="Sample Artist",
            duration=120,
            raw_formats=[
                {"format_id": "137", "ext": "mp4", "height": 1080, "vcodec": "avc1", "acodec": "none", "filesize": 40_000_000},
                {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "filesize": 5_000_000},
            ],
            subtitles={"en": [{"ext": "vtt"}]},
        )
        rec = SmartRecommendation(
            quality="1080p",
            format="MP4",
            mode=DownloadMode.VIDEO_AUDIO,
            estimated_size=45_000_000,
            label="1080p · MP4 · ~45 MB",
        )

        opts.populate(metadata, rec)
        self.assertEqual(opts.get_quality(), "1080p")
        self.assertEqual(opts.get_mode(), DownloadMode.VIDEO_AUDIO)
        self.assertEqual(opts.get_format(), "MP4")
        self.assertEqual(opts.get_destination(), "/tmp/downloads")

        # Test destination change
        opts.set_destination("/home/user/Videos")
        self.assertEqual(opts.get_destination(), "/home/user/Videos")

        # Test clipping via visual selector
        opts._clip_selector._timeline.set_range(60.0, 120.0)
        # Note metadata duration was 120 so max is 120
        opts._clip_selector._timeline.set_range(60.0, 110.0)
        start, end = opts.get_clip_range()
        self.assertEqual(start, "00:01:00")
        self.assertEqual(end, "00:01:50")

        # Full range returns None, None
        opts._clip_selector._timeline.set_range(0.0, 120.0)
        start, end = opts.get_clip_range()
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_clip_selector_view(self):
        """Test ClipSelectorView duration, range sync, and download clip callback."""
        from app.views.clip_selector import ClipSelectorView

        clip_dl_args = None
        def on_clip_dl(s, e):
            nonlocal clip_dl_args
            clip_dl_args = (s, e)

        selector = ClipSelectorView(on_download_clip=on_clip_dl)
        metadata = VideoMetadata(title="Trim Test", duration=300)
        selector.set_metadata(metadata)

        self.assertEqual(selector._lbl_start_bound.get_label(), "00:00")
        self.assertEqual(selector._lbl_end_bound.get_label(), "5:00")

        # Set range to 10s -> 70s
        selector._timeline.set_range(10.0, 70.0)
        selector._update_readouts(10.0, 70.0)
        self.assertIn("1:00", selector._duration_badge.get_label())
        self.assertEqual(selector._entry_start.get_text(), "00:00:10")
        self.assertEqual(selector._entry_end.get_text(), "00:01:10")

        # Test download clip button
        selector._on_download_clip_clicked(None)
        self.assertEqual(clip_dl_args, ("00:00:10", "00:01:10"))

    def test_queue_view_and_task_row(self):
        """Test QueueView row updates for various task statuses."""
        mock_downloader = MagicMock()
        mock_history = MagicMock()
        queue = DownloadQueue(downloader_service=mock_downloader, history_service=mock_history)

        task = DownloadTask(
            id="task01",
            url="https://youtube.com/watch?v=abc",
            title="Queue Task Video",
            quality="1080p",
            output_format="MP4",
            mode=DownloadMode.VIDEO_AUDIO,
            destination="/tmp",
            status=DownloadStatus.WAITING,
        )

        row = TaskRow(task, queue)
        self.assertEqual(row.task_id, "task01")
        self.assertIn("Queued", row._detail_label.get_label())

        # Update to DOWNLOADING
        task.status = DownloadStatus.DOWNLOADING
        task.progress = 45.0
        task.downloaded_bytes = 45_000_000
        task.total_bytes = 100_000_000
        task.speed = 5_000_000.0
        task.eta = 11
        row.update(task)
        self.assertTrue(row._progress_bar.get_visible())
        self.assertIn("45%", row._detail_label.get_label())

        # Update to PROCESSING
        task.status = DownloadStatus.PROCESSING
        task.processing_step = "Merging audio and video streams…"
        row.update(task)
        self.assertEqual(row._detail_label.get_label(), "Merging audio and video streams…")

        # Update to COMPLETED
        task.status = DownloadStatus.COMPLETED
        row.update(task)
        self.assertFalse(row._progress_bar.get_visible())
        self.assertEqual(row._detail_label.get_label(), "Completed")

        # Update to FAILED
        task.status = DownloadStatus.FAILED
        task.error_message = "Network error"
        row.update(task)
        self.assertIn("Network error", row._detail_label.get_label())

        # Test QueueView integration
        qview = QueueView(queue)
        qview._on_task_added(task)
        self.assertTrue(qview.get_visible())
        self.assertIn("task01", qview._rows)

        qview._on_task_removed("task01")
        self.assertNotIn("task01", qview._rows)
        self.assertFalse(qview.get_visible())

    def test_history_dialog_and_row(self):
        """Test HistoryDialog and HistoryRow."""
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp.close()

        hist_service = HistoryService(filepath=tmp.name)
        item = HistoryItem(
            id="h01",
            title="Historical Video",
            url="https://youtube.com/watch?v=xyz",
            provider="YouTube",
            date="2026-10-04 12:00",
            filepath="/tmp/nonexistent.mp4",
            output_format="MP4",
            quality="1080p",
            filesize=10485760,
        )
        hist_service.add_item(item)

        row = HistoryRow(item, hist_service, on_removed=None)
        self.assertEqual(row.item.id, "h01")

        parent_win = Gtk.Window()
        dialog = HistoryDialog(parent_window=parent_win, history_service=hist_service)
        self.assertEqual(dialog._stack.get_visible_child_name(), "list")

        # Test Clear all
        dialog._clear_btn.emit("clicked")
        self.assertEqual(dialog._stack.get_visible_child_name(), "empty")
        self.assertEqual(len(hist_service.get_items()), 0)

        try:
            os.remove(tmp.name)
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
