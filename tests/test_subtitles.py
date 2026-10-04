"""Unit tests for the SubtitleService."""

import unittest

from app.models import VideoMetadata
from app.subtitles import SubtitleService


class TestSubtitleService(unittest.TestCase):
    def setUp(self):
        self.service = SubtitleService()

    def test_get_available_subtitles(self):
        metadata = VideoMetadata(
            title="Subtitles Test",
            uploader="Channel",
            duration=300,
            subtitles={
                "en": [{"ext": "vtt"}],
                "fr": [{"ext": "vtt"}],
            },
            automatic_captions={
                "es": [{"ext": "vtt"}],
                "en": [{"ext": "vtt"}],  # duplicate of manual, manual should take priority
            },
        )
        subs = self.service.get_available_subtitles(metadata)
        codes = [s[0] for s in subs]
        self.assertIn("en", codes)
        self.assertIn("fr", codes)
        self.assertIn("es", codes)

        # Check that manual 'en' is marked as not auto
        en_item = next(s for s in subs if s[0] == "en")
        self.assertFalse(en_item[2])  # is_auto == False

        # Check that 'es' is marked as auto
        es_item = next(s for s in subs if s[0] == "es")
        self.assertTrue(es_item[2])  # is_auto == True

    def test_get_subtitle_options_none(self):
        opts = self.service.get_subtitle_options(None)
        self.assertEqual(opts, {})
        opts = self.service.get_subtitle_options("none")
        self.assertEqual(opts, {})

    def test_get_subtitle_options_enabled(self):
        opts = self.service.get_subtitle_options("en", embed=False)
        self.assertTrue(opts["writesubtitles"])
        self.assertEqual(opts["subtitleslangs"], ["en"])
        self.assertNotIn("postprocessors", opts)

    def test_get_subtitle_options_embed(self):
        opts = self.service.get_subtitle_options("fr", embed=True)
        self.assertTrue(opts["writesubtitles"])
        self.assertIn("postprocessors", opts)
        self.assertEqual(opts["postprocessors"][0]["key"], "FFmpegEmbedSubtitle")


if __name__ == "__main__":
    unittest.main()
