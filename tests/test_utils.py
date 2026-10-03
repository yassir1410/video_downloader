import unittest
from app.utils import format_duration, format_file_size, format_speed, format_eta, is_valid_url


class TestFormatDuration(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_duration(0), "0:00")

    def test_seconds_only(self):
        self.assertEqual(format_duration(5), "0:05")
        self.assertEqual(format_duration(59), "0:59")

    def test_minutes_and_seconds(self):
        self.assertEqual(format_duration(60), "1:00")
        self.assertEqual(format_duration(61), "1:01")
        self.assertEqual(format_duration(872), "14:32")

    def test_hours(self):
        self.assertEqual(format_duration(3600), "1:00:00")
        self.assertEqual(format_duration(3661), "1:01:01")
        self.assertEqual(format_duration(5058), "1:24:18")

    def test_negative(self):
        self.assertEqual(format_duration(-1), "0:00")


class TestFormatFileSize(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_file_size(0), "0 B")

    def test_bytes(self):
        self.assertEqual(format_file_size(500), "500 B")

    def test_kilobytes(self):
        self.assertEqual(format_file_size(1024), "1.0 KB")
        self.assertEqual(format_file_size(1536), "1.5 KB")

    def test_megabytes(self):
        self.assertEqual(format_file_size(1048576), "1.0 MB")
        self.assertEqual(format_file_size(125829120), "120.0 MB")

    def test_gigabytes(self):
        self.assertEqual(format_file_size(1073741824), "1.0 GB")

    def test_negative(self):
        self.assertEqual(format_file_size(-100), "0 B")


class TestFormatSpeed(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_speed(0), "0 B/s")

    def test_bytes(self):
        self.assertEqual(format_speed(500), "500 B/s")

    def test_kilobytes(self):
        self.assertEqual(format_speed(1024), "1.0 KB/s")

    def test_megabytes(self):
        self.assertEqual(format_speed(8500000), "8.1 MB/s")

    def test_negative(self):
        self.assertEqual(format_speed(-100), "0 B/s")


class TestFormatEta(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_eta(0), "0 sec remaining")

    def test_seconds(self):
        self.assertEqual(format_eta(14), "14 sec remaining")

    def test_minutes_exact(self):
        self.assertEqual(format_eta(60), "1 min remaining")

    def test_minutes_and_seconds(self):
        self.assertEqual(format_eta(125), "2 min 5 sec remaining")

    def test_hours(self):
        self.assertEqual(format_eta(3661), "1 hr 1 min remaining")

    def test_negative(self):
        self.assertEqual(format_eta(-5), "0 sec remaining")


class TestIsValidUrl(unittest.TestCase):
    def test_valid_http(self):
        self.assertTrue(is_valid_url("http://example.com"))

    def test_valid_https(self):
        self.assertTrue(is_valid_url("https://www.youtube.com/watch?v=abc"))

    def test_invalid_no_scheme(self):
        self.assertFalse(is_valid_url("www.youtube.com"))

    def test_invalid_empty(self):
        self.assertFalse(is_valid_url(""))

    def test_invalid_none(self):
        self.assertFalse(is_valid_url(None))

    def test_invalid_random_text(self):
        self.assertFalse(is_valid_url("hello world"))

    def test_whitespace_stripped(self):
        self.assertTrue(is_valid_url("  https://example.com  "))


if __name__ == "__main__":
    unittest.main()
