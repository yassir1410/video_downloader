"""Unit tests for the DownloadQueue service."""

import time
import unittest
from unittest.mock import MagicMock

from app.models import (
    DownloadMode,
    DownloadProgress,
    DownloadStatus,
    DownloadTask,
)
from app.queue import DownloadQueue


class TestDownloadQueue(unittest.TestCase):
    def setUp(self):
        self.mock_downloader = MagicMock()
        self.mock_downloader.download.return_value = "/tmp/video.mp4"
        self.mock_history = MagicMock()
        self.queue = DownloadQueue(
            downloader_service=self.mock_downloader,
            history_service=self.mock_history,
        )

    def tearDown(self):
        self.queue._running = False
        self.queue._wake_event.set()

    def test_add_and_get_tasks(self):
        task = DownloadTask(
            id="t1",
            url="https://www.youtube.com/watch?v=123",
            title="Video 1",
            quality="1080p",
            output_format="MP4",
            destination="/tmp",
        )
        tid = self.queue.add_task(task)
        self.assertEqual(tid, "t1")
        self.assertIsNotNone(self.queue.get_task("t1"))

    def test_sequential_processing(self):
        t1 = DownloadTask(
            id="t1",
            url="https://www.youtube.com/watch?v=1",
            title="Video 1",
            destination="/tmp",
        )
        t2 = DownloadTask(
            id="t2",
            url="https://www.youtube.com/watch?v=2",
            title="Video 2",
            destination="/tmp",
        )
        self.queue.add_task(t1)
        self.queue.add_task(t2)

        # Wait for worker thread to process tasks
        for _ in range(50):
            if t1.status == DownloadStatus.COMPLETED and t2.status == DownloadStatus.COMPLETED:
                break
            time.sleep(0.05)

        self.assertEqual(t1.status, DownloadStatus.COMPLETED)
        self.assertEqual(t2.status, DownloadStatus.COMPLETED)
        self.assertEqual(self.mock_downloader.download.call_count, 2)

    def test_cancel_waiting_task(self):
        t1 = DownloadTask(
            id="t1",
            url="https://www.youtube.com/watch?v=1",
            title="Video 1",
            destination="/tmp",
        )
        self.queue.add_task(t1)
        self.queue.cancel_task("t1")
        self.assertIn(t1.status, (DownloadStatus.CANCELLED, DownloadStatus.COMPLETED))

    def test_clear_completed(self):
        t1 = DownloadTask(
            id="t1",
            url="https://www.youtube.com/watch?v=1",
            title="Video 1",
            status=DownloadStatus.COMPLETED,
        )
        t2 = DownloadTask(
            id="t2",
            url="https://www.youtube.com/watch?v=2",
            title="Video 2",
            status=DownloadStatus.WAITING,
        )
        self.queue._tasks = [t1, t2]
        self.queue.clear_completed()
        tasks = self.queue.get_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "t2")


if __name__ == "__main__":
    unittest.main()
