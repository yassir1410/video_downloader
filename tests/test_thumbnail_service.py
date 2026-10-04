"""Unit tests for ThumbnailService."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.models import VideoMetadata
from app.thumbnail_service import ThumbnailService


class TestThumbnailService(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.service = ThumbnailService(cache_dir=self.tmp_dir)

    def tearDown(self):
        self.service._running = False
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_get_stream_url_prioritizes_low_res_video(self):
        """Test that stream URL selection picks 240p/360p video stream for lightweight thumbnails."""
        metadata = VideoMetadata(
            title="Test Stream",
            raw_formats=[
                {"format_id": "140", "vcodec": "none", "acodec": "mp4a", "url": "http://audio.mp4"},
                {"format_id": "137", "vcodec": "avc1", "height": 1080, "url": "http://1080p.mp4"},
                {"format_id": "134", "vcodec": "avc1", "height": 360, "url": "http://360p.mp4", "http_headers": {"User-Agent": "TestUA"}},
                {"format_id": "133", "vcodec": "avc1", "height": 240, "url": "http://240p.mp4"},
            ],
        )

        stream_info = self.service.get_stream_url(metadata)
        self.assertIsNotNone(stream_info)
        url, headers = stream_info
        # 240p or 360p has score 0
        self.assertIn(url, ["http://240p.mp4", "http://360p.mp4"])

    def test_get_stream_url_empty(self):
        """Test stream URL returns None when no video formats exist."""
        metadata = VideoMetadata(title="Empty", raw_formats=[])
        self.assertIsNone(self.service.get_stream_url(metadata))

    def test_cache_path_generation(self):
        """Test deterministic cache path generation."""
        path1 = self.service._get_cache_path("http://example.com/video.mp4", 12.345)
        path2 = self.service._get_cache_path("http://example.com/video.mp4", 12.349)
        # Should be identical because of round(t, 2)
        self.assertEqual(path1, path2)
        self.assertTrue(path1.endswith(".jpg"))

    @patch("subprocess.run")
    def test_extract_frame_sync_invokes_ffmpeg(self, mock_run):
        """Test that FFmpeg is invoked with proper range seeking parameters."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        # Create dummy file to simulate FFmpeg writing output
        def side_effect(cmd, **kwargs):
            out_file = cmd[-1]
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(b"\xff\xd8\xff\xe0" + b"0" * 100)
            return mock_proc

        mock_run.side_effect = side_effect

        res = self.service.extract_frame_sync("http://example.com/video.mp4", 5.0)
        self.assertIsNotNone(res)
        self.assertTrue(os.path.exists(res))

        # Verify command flags
        cmd_args = mock_run.call_args[0][0]
        self.assertIn("-ss", cmd_args)
        self.assertIn("5.000", cmd_args)
        self.assertIn("-vframes", cmd_args)
        self.assertIn("1", cmd_args)


if __name__ == "__main__":
    unittest.main()
