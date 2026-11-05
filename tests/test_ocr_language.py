"""Offline OCR language preferences and command-argument safety."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from clipmint.ocr import extract_text, validate_language, OcrWorker


class OcrLanguageTests(unittest.TestCase):
    def test_accept_installed_tesseract_language_codes(self):
        for code in ("eng", "afr", "eng+afr", "jpn+eng+afr"):
            self.assertEqual(validate_language(code), code)

    def test_reject_malformed_or_untrusted_language_values(self):
        for code in ("", "en", "ENg", "eng;touch /tmp/unsafe",
                     "-c", "eng+../", "eng+eng+eng+eng+eng"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                validate_language(code)

    def test_language_passed_as_single_argument(self):
        png = b"\x89PNG\r\n\x1a\n" + b"fake png"
        proc = SimpleNamespace(returncode=0, stdout=b"offline text")
        with patch("clipmint.ocr.subprocess.run", return_value=proc) as run:
            self.assertEqual(extract_text(
                png, executable="fake-tesseract", language="eng+afr"
            ), "offline text")
        self.assertEqual(run.call_args.args[0],
                         ["fake-tesseract", "stdin", "stdout", "-l", "eng+afr"])
        worker = OcrWorker(png, language="afr")
        self.assertEqual(worker.language, "afr")


if __name__ == "__main__":
    unittest.main()
