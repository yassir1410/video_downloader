import unittest
from app.formats import FormatService
from app.models import DownloadMode, VideoMetadata


class TestGetAvailableQualities(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_basic_formats(self):
        metadata = VideoMetadata(
            title="Test", uploader="Test", duration=600,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "18", "height": 360, "ext": "mp4", "vcodec": "avc1"},
                {"format_id": "22", "height": 720, "ext": "mp4", "vcodec": "avc1"},
                {"format_id": "137", "height": 1080, "ext": "mp4", "vcodec": "avc1"},
            ]
        )
        qualities = self.service.get_available_qualities(metadata)
        self.assertEqual(qualities[0], "Best")
        self.assertIn("1080p", qualities)
        self.assertIn("720p", qualities)
        self.assertIn("360p", qualities)

    def test_deduplication(self):
        metadata = VideoMetadata(
            title="Test", uploader="Test", duration=600,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "137", "height": 1080, "ext": "mp4", "vcodec": "avc1"},
                {"format_id": "248", "height": 1080, "ext": "webm", "vcodec": "vp9"},
                {"format_id": "399", "height": 1080, "ext": "mp4", "vcodec": "av01"},
            ]
        )
        qualities = self.service.get_available_qualities(metadata)
        # Should only have one 1080p entry
        self.assertEqual(qualities.count("1080p"), 1)

    def test_sorted_high_to_low(self):
        metadata = VideoMetadata(
            title="Test", uploader="Test", duration=600,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "1", "height": 360, "ext": "mp4", "vcodec": "avc1"},
                {"format_id": "2", "height": 2160, "ext": "mp4", "vcodec": "avc1"},
                {"format_id": "3", "height": 720, "ext": "mp4", "vcodec": "avc1"},
                {"format_id": "4", "height": 1080, "ext": "mp4", "vcodec": "avc1"},
            ]
        )
        qualities = self.service.get_available_qualities(metadata)
        # After 'Best', should be 2160p, 1080p, 720p, 360p
        non_best = qualities[1:]
        heights = []
        for q in non_best:
            h = int(q.split("p")[0])
            heights.append(h)
        self.assertEqual(heights, sorted(heights, reverse=True))

    def test_audio_only_formats_excluded(self):
        metadata = VideoMetadata(
            title="Test", uploader="Test", duration=600,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "140", "height": None, "ext": "m4a", "vcodec": "none"},
                {"format_id": "251", "height": None, "ext": "webm", "vcodec": "none"},
                {"format_id": "22", "height": 720, "ext": "mp4", "vcodec": "avc1"},
            ]
        )
        qualities = self.service.get_available_qualities(metadata)
        self.assertEqual(len(qualities), 2)  # Best + 720p

    def test_empty_formats(self):
        metadata = VideoMetadata(
            title="Test", uploader="Test", duration=600,
            thumbnail_url="", webpage_url="",
            raw_formats=[]
        )
        qualities = self.service.get_available_qualities(metadata)
        self.assertEqual(qualities, ["Best"])


class TestGetOutputFormats(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_video_audio(self):
        formats = self.service.get_output_formats(DownloadMode.VIDEO_AUDIO)
        self.assertEqual(formats, ["MP4", "WebM"])

    def test_audio_only(self):
        formats = self.service.get_output_formats(DownloadMode.AUDIO_ONLY)
        self.assertEqual(formats, ["MP3", "M4A", "Opus"])


class TestGetFormatSelector(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_best_mp4(self):
        selector = self.service.get_format_selector("Best", DownloadMode.VIDEO_AUDIO, "MP4")
        self.assertIn("bestvideo", selector)
        self.assertIn("bestaudio", selector)
        self.assertIn("mp4", selector)

    def test_1080p_mp4(self):
        selector = self.service.get_format_selector("1080p", DownloadMode.VIDEO_AUDIO, "MP4")
        self.assertIn("height<=1080", selector)
        self.assertIn("mp4", selector)

    def test_audio_only(self):
        selector = self.service.get_format_selector("Best", DownloadMode.AUDIO_ONLY, "MP3")
        self.assertEqual(selector, "bestaudio/best")

    def test_webm(self):
        selector = self.service.get_format_selector("720p", DownloadMode.VIDEO_AUDIO, "WebM")
        self.assertIn("height<=720", selector)
        self.assertIn("webm", selector)


class TestGetPostprocessors(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_mp3(self):
        pp = self.service.get_postprocessors(DownloadMode.AUDIO_ONLY, "MP3")
        self.assertEqual(len(pp), 1)
        self.assertEqual(pp[0]["key"], "FFmpegExtractAudio")
        self.assertEqual(pp[0]["preferredcodec"], "mp3")

    def test_m4a(self):
        pp = self.service.get_postprocessors(DownloadMode.AUDIO_ONLY, "M4A")
        self.assertEqual(pp[0]["preferredcodec"], "m4a")

    def test_video_no_postprocessors(self):
        pp = self.service.get_postprocessors(DownloadMode.VIDEO_AUDIO, "MP4")
        self.assertEqual(pp, [])


class TestParseHeight(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_standard(self):
        self.assertEqual(self.service._parse_height("1080p"), 1080)
        self.assertEqual(self.service._parse_height("720p"), 720)

    def test_4k(self):
        self.assertEqual(self.service._parse_height("2160p (4K)"), 2160)

    def test_best(self):
        self.assertIsNone(self.service._parse_height("Best"))


if __name__ == "__main__":
    unittest.main()
