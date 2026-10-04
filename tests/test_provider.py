"""Unit tests for video provider detection."""

import unittest

from app.models import VideoProvider
from app.utils import detect_provider


class TestDetectProvider(unittest.TestCase):
    def test_youtube_urls(self):
        urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/abcdef12345",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(detect_provider(url), VideoProvider.YOUTUBE)

    def test_facebook_urls(self):
        urls = [
            "https://www.facebook.com/example/videos/1234567890/",
            "https://facebook.com/watch/?v=1234567890",
            "https://fb.watch/xyz123abc/",
            "https://www.facebook.com/reel/9876543210",
            "https://m.facebook.com/story.php?story_fbid=123&id=456",
            "https://web.facebook.com/watch/?v=123456789",
            "https://www.facebook.com/share/v/19QabcXYZ/",
            "https://www.facebook.com/share/r/19QabcXYZ/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(detect_provider(url), VideoProvider.FACEBOOK)

    def test_other_providers(self):
        urls = [
            "https://vimeo.com/12345678",
            "https://www.dailymotion.com/video/x7tgad0",
            "https://twitter.com/example/status/123456",
            "https://x.com/example/status/123456",
            "https://example.com/video.mp4",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(detect_provider(url), VideoProvider.OTHER)

    def test_invalid_and_empty(self):
        self.assertEqual(detect_provider(""), VideoProvider.OTHER)
        self.assertEqual(detect_provider(None), VideoProvider.OTHER)
        self.assertEqual(detect_provider("not a url"), VideoProvider.OTHER)
        self.assertEqual(detect_provider("http://"), VideoProvider.OTHER)


if __name__ == "__main__":
    unittest.main()
