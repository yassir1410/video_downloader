"""Unit tests for TimelineWidget."""

import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GdkPixbuf, Gtk

from app.views.timeline import TimelineWidget

app = Adw.Application(application_id="io.github.videodownloader.TimelineTests")


class TestTimelineWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app

    def test_initialization_and_range(self):
        """Test default duration and range clamping."""
        timeline = TimelineWidget(duration=120.0)
        start, end = timeline.get_range()
        self.assertEqual(start, 0.0)
        self.assertEqual(end, 120.0)

        # Set range within bounds
        timeline.set_range(15.0, 45.0)
        start, end = timeline.get_range()
        self.assertEqual(start, 15.0)
        self.assertEqual(end, 45.0)

        # Set range out of bounds (should clamp)
        timeline.set_range(-10.0, 200.0)
        start, end = timeline.get_range()
        self.assertEqual(start, 0.0)
        self.assertEqual(end, 120.0)

    def test_coordinate_conversions(self):
        """Test time_to_x and x_to_time precision."""
        timeline = TimelineWidget(duration=100.0)
        width = 500.0

        # At zoom 1.0
        self.assertAlmostEqual(timeline._time_to_x(0.0, width), 0.0)
        self.assertAlmostEqual(timeline._time_to_x(50.0, width), 250.0)
        self.assertAlmostEqual(timeline._time_to_x(100.0, width), 500.0)

        self.assertAlmostEqual(timeline._x_to_time(0.0, width), 0.0)
        self.assertAlmostEqual(timeline._x_to_time(250.0, width), 500.0 * 0.5 * 100.0 / 500.0)
        self.assertAlmostEqual(timeline._x_to_time(500.0, width), 100.0)

    def test_nudging(self):
        """Test keyboard nudging of active handles."""
        timeline = TimelineWidget(duration=60.0)
        timeline.set_range(10.0, 50.0)

        # Active handle defaults to start
        timeline._active_handle = "start"
        timeline.nudge_active(1.0)
        start, end = timeline.get_range()
        self.assertEqual(start, 11.0)
        self.assertEqual(end, 50.0)

        timeline.nudge_active(-5.0)
        start, end = timeline.get_range()
        self.assertEqual(start, 6.0)

        # Switch to end
        timeline._active_handle = "end"
        timeline.nudge_active(-2.0)
        start, end = timeline.get_range()
        self.assertEqual(end, 48.0)

        timeline.nudge_active(10.0)
        start, end = timeline.get_range()
        self.assertEqual(end, 58.0)

    def test_zoom(self):
        """Test zoom levels clamping."""
        timeline = TimelineWidget(duration=120.0)
        self.assertEqual(timeline.get_zoom(), 1.0)

        timeline.set_zoom(2.5)
        self.assertEqual(timeline.get_zoom(), 2.5)

        timeline.set_zoom(10.0)  # max clamp 5.0
        self.assertEqual(timeline.get_zoom(), 5.0)

        timeline.set_zoom(0.2)  # min clamp 1.0
        self.assertEqual(timeline.get_zoom(), 1.0)

    def test_filmstrip_tile_addition(self):
        """Test setting filmstrip tiles."""
        timeline = TimelineWidget(duration=60.0)
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 40, 30)
        timeline.set_filmstrip_tile(0, pb, total_count=4)
        self.assertEqual(len(timeline._filmstrip_pixbufs), 4)
        self.assertIsNotNone(timeline._filmstrip_pixbufs[0])
        self.assertIsNone(timeline._filmstrip_pixbufs[1])


if __name__ == "__main__":
    unittest.main()
