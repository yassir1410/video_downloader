"""Unit tests for the HistoryService."""

import os
import tempfile
import unittest

from app.history import HistoryService
from app.models import HistoryItem


class TestHistoryService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.history_file = os.path.join(self.temp_dir, "test_history.json")
        self.service = HistoryService(filepath=self.history_file)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_and_get_items(self):
        item = HistoryItem(
            id="h1",
            title="History Video 1",
            url="https://youtube.com/watch?v=1",
            provider="YouTube",
            date="2026-10-04 10:00",
            filepath="/tmp/v1.mp4",
            output_format="MP4",
            quality="1080p",
            filesize=50000000,
        )
        self.service.add_item(item)
        items = self.service.get_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "h1")
        self.assertEqual(items[0].title, "History Video 1")

    def test_remove_item(self):
        item1 = HistoryItem(id="h1", title="V1", url="u1", provider="YouTube", date="", filepath="", output_format="MP4", quality="1080p")
        item2 = HistoryItem(id="h2", title="V2", url="u2", provider="Facebook", date="", filepath="", output_format="MP4", quality="720p")
        self.service.add_item(item1)
        self.service.add_item(item2)

        self.service.remove_item("h1")
        items = self.service.get_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "h2")

    def test_clear_history(self):
        item = HistoryItem(id="h1", title="V1", url="u1", provider="YouTube", date="", filepath="", output_format="MP4", quality="1080p")
        self.service.add_item(item)
        self.service.clear_history()
        self.assertEqual(self.service.get_items(), [])


if __name__ == "__main__":
    unittest.main()
