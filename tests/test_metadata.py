import unittest
from unittest.mock import patch, MagicMock

from app.metadata import MetadataService, MetadataError
from app.models import VideoMetadata


MOCK_INFO = {
    "title": "Test Video - Building a REST API",
    "uploader": "Test Channel",
    "channel": "Test Channel",
    "duration": 872,
    "thumbnail": "https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "formats": [
        {
            "format_id": "18",
            "height": 360,
            "ext": "mp4",
            "vcodec": "avc1.42001E",
            "acodec": "mp4a.40.2",
            "filesize": 25000000,
        },
        {
            "format_id": "22",
            "height": 720,
            "ext": "mp4",
            "vcodec": "avc1.64001F",
            "acodec": "mp4a.40.2",
            "filesize": 75000000,
        },
        {
            "format_id": "137",
            "height": 1080,
            "ext": "mp4",
            "vcodec": "avc1.640028",
            "acodec": "none",
            "filesize": 150000000,
        },
        {
            "format_id": "140",
            "height": None,
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "filesize": 10000000,
        },
    ],
}


MOCK_FACEBOOK_INFO = {
    "id": "123456",
    "title": "Facebook Video - Cooking Tutorial",
    "uploader": "Cooking Page",
    "duration": 42,
    "thumbnail": "https://example.com/fb_thumb.jpg",
    "webpage_url": "https://www.facebook.com/cooking/videos/123456",
    "formats": [
        {"format_id": "sd", "height": 480, "ext": "mp4"},
        {"format_id": "hd", "height": 720, "ext": "mp4"},
    ],
}


class TestMetadataService(unittest.TestCase):
    def setUp(self):
        self.service = MetadataService()

    @patch("app.metadata.yt_dlp.YoutubeDL")
    def test_extract_success(self, mock_ydl_class):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = MOCK_INFO
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_class.return_value = mock_ydl

        result = self.service.extract("https://www.youtube.com/watch?v=abc123")

        self.assertIsInstance(result, VideoMetadata)
        self.assertEqual(result.title, "Test Video - Building a REST API")
        self.assertEqual(result.uploader, "Test Channel")
        self.assertEqual(result.duration, 872)
        self.assertEqual(len(result.raw_formats), 4)

    @patch("app.metadata.yt_dlp.YoutubeDL")
    def test_extract_facebook_video(self, mock_ydl_class):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = MOCK_FACEBOOK_INFO
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_class.return_value = mock_ydl

        result = self.service.extract("https://www.facebook.com/cooking/videos/123456")

        self.assertIsInstance(result, VideoMetadata)
        self.assertEqual(result.title, "Facebook Video - Cooking Tutorial")
        self.assertEqual(result.uploader, "Cooking Page")
        self.assertEqual(result.duration, 42)
        self.assertEqual(result.provider.value, "Facebook")
        self.assertEqual(len(result.raw_formats), 2)

    @patch("app.metadata.yt_dlp.YoutubeDL")
    def test_extract_facebook_missing_metadata(self, mock_ydl_class):
        info = {
            "id": "123456",
            "title": "",
            "description": "Short description of the video\nSecond line",
            "uploader": None,
            "duration": None,
            "thumbnail": None,
            "webpage_url": "https://fb.watch/xyz123",
            "formats": [],
        }

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_class.return_value = mock_ydl

        result = self.service.extract("https://fb.watch/xyz123")

        self.assertEqual(result.title, "Short description of the video")
        self.assertEqual(result.uploader, "Facebook")
        self.assertIsNone(result.duration)
        self.assertEqual(result.thumbnail_url, "")
        self.assertEqual(result.provider.value, "Facebook")

    @patch("app.metadata.yt_dlp.YoutubeDL")
    def test_extract_missing_uploader_uses_channel(self, mock_ydl_class):
        info = dict(MOCK_INFO)
        info["uploader"] = None
        info["channel"] = "Fallback Channel"

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_class.return_value = mock_ydl

        result = self.service.extract("https://www.youtube.com/watch?v=abc123")
        self.assertEqual(result.uploader, "Fallback Channel")

    @patch("app.metadata.yt_dlp.YoutubeDL")
    def test_extract_returns_none_raises_error(self, mock_ydl_class):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = None
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_class.return_value = mock_ydl

        with self.assertRaises(MetadataError) as ctx:
            self.service.extract("https://example.com/bad")
        self.assertIn("Could not retrieve", ctx.exception.user_message)


class TestClassifyError(unittest.TestCase):
    def setUp(self):
        self.service = MetadataService()

    def test_private_video(self):
        msg = self.service._classify_error("this video is private")
        self.assertIn("private", msg.lower())

    def test_unavailable(self):
        msg = self.service._classify_error("video unavailable")
        self.assertIn("unavailable", msg.lower())

    def test_age_restricted(self):
        msg = self.service._classify_error("sign in to confirm your age")
        self.assertIn("authentication", msg.lower())

    def test_geo_restricted(self):
        msg = self.service._classify_error("not available in your country")
        self.assertIn("region", msg.lower())

    def test_facebook_restricted(self):
        from app.models import VideoProvider
        msg = self.service._classify_error("cannot parse data", VideoProvider.FACEBOOK)
        self.assertIn("facebook", msg.lower())
        self.assertIn("private", msg.lower())

    def test_unsupported_website(self):
        msg = self.service._classify_error("unsupported url")
        self.assertIn("not currently supported", msg.lower())

    def test_network_error(self):
        msg = self.service._classify_error("network connection timed out")
        self.assertIn("network", msg.lower())

    def test_unknown_error(self):
        msg = self.service._classify_error("some unknown error xyz")
        self.assertIn("unable to access", msg.lower())


if __name__ == "__main__":
    unittest.main()
