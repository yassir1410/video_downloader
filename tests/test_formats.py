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

    def test_facebook_sd_hd_formats(self):
        metadata = VideoMetadata(
            title="Facebook Video", uploader="Page", duration=120,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "sd", "ext": "mp4", "height": 480},
                {"format_id": "hd", "ext": "mp4", "height": 720},
            ]
        )
        qualities = self.service.get_available_qualities(metadata)
        self.assertEqual(qualities, ["Best", "720p", "480p"])

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


class TestCalculateEstimatedSize(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_combined_video_audio_size(self):
        metadata = VideoMetadata(
            title="Combined Test", uploader="Author", duration=100,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "18", "height": 360, "ext": "mp4", "filesize": 25000000, "acodec": "mp4a", "vcodec": "avc1"},
                {"format_id": "22", "height": 720, "ext": "mp4", "filesize": 75000000, "acodec": "mp4a", "vcodec": "avc1"},
            ]
        )
        size_720 = self.service.calculate_estimated_size(metadata, "720p", "MP4", DownloadMode.VIDEO_AUDIO)
        self.assertEqual(size_720, 75000000)

    def test_separate_video_and_audio_streams(self):
        metadata = VideoMetadata(
            title="Separate Streams", uploader="Author", duration=100,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "137", "height": 1080, "ext": "mp4", "filesize": 100000000, "acodec": "none", "vcodec": "avc1"},
                {"format_id": "140", "height": None, "ext": "m4a", "filesize": 10000000, "acodec": "mp4a", "vcodec": "none"},
            ]
        )
        size_1080 = self.service.calculate_estimated_size(metadata, "1080p", "MP4", DownloadMode.VIDEO_AUDIO)
        self.assertEqual(size_1080, 110000000)  # 100MB + 10MB

    def test_audio_only_size(self):
        metadata = VideoMetadata(
            title="Audio Test", uploader="Author", duration=100,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "140", "height": None, "ext": "m4a", "filesize": 12000000, "acodec": "mp4a", "vcodec": "none"},
            ]
        )
        size_audio = self.service.calculate_estimated_size(metadata, "Best", "MP3", DownloadMode.AUDIO_ONLY)
        self.assertEqual(size_audio, 12000000)


class TestGetSmartRecommendation(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_prioritizes_1080p(self):
        metadata = VideoMetadata(
            title="1080p Available", uploader="Author", duration=100,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "137", "height": 1080, "ext": "mp4", "filesize": 50000000, "vcodec": "avc1", "acodec": "mp4a"},
                {"format_id": "313", "height": 2160, "ext": "webm", "filesize": 250000000, "vcodec": "vp9", "acodec": "none"},
                {"format_id": "22", "height": 720, "ext": "mp4", "filesize": 25000000, "vcodec": "avc1", "acodec": "mp4a"},
            ]
        )
        rec = self.service.get_smart_recommendation(metadata)
        self.assertEqual(rec.quality, "1080p")
        self.assertEqual(rec.format, "MP4")
        self.assertEqual(rec.mode, DownloadMode.VIDEO_AUDIO)
        self.assertIn("1080p", rec.label)
        self.assertIn("MP4", rec.label)

    def test_falls_back_to_720p_if_no_1080p(self):
        metadata = VideoMetadata(
            title="720p Max", uploader="Author", duration=100,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "22", "height": 720, "ext": "mp4", "filesize": 25000000, "vcodec": "avc1", "acodec": "mp4a"},
                {"format_id": "18", "height": 360, "ext": "mp4", "filesize": 10000000, "vcodec": "avc1", "acodec": "mp4a"},
            ]
        )
        rec = self.service.get_smart_recommendation(metadata)
        self.assertEqual(rec.quality, "720p")
        self.assertEqual(rec.format, "MP4")

    def test_falls_back_to_best_if_only_best(self):
        metadata = VideoMetadata(
            title="Unknown Heights", uploader="Author", duration=100,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "video", "ext": "mp4", "vcodec": "avc1"},
            ]
        )
        rec = self.service.get_smart_recommendation(metadata)
        self.assertEqual(rec.quality, "Best")


class TestGetAvailableQualitiesWithDetails(unittest.TestCase):
    def setUp(self):
        self.service = FormatService()

    def test_includes_size_in_label(self):
        metadata = VideoMetadata(
            title="Details Test", uploader="Author", duration=100,
            thumbnail_url="", webpage_url="",
            raw_formats=[
                {"format_id": "22", "height": 720, "ext": "mp4", "filesize": 52428800, "vcodec": "avc1", "acodec": "mp4a"},
            ]
        )
        details = self.service.get_available_qualities_with_details(metadata)
        # Should contain ('720p', '720p (~50.0 MB)')
        qualities_dict = dict(details)
        self.assertIn("720p", qualities_dict)
        self.assertIn("50.0 MB", qualities_dict["720p"])


if __name__ == "__main__":
    unittest.main()
