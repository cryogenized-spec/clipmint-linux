"""Contracts for the extracted OCR orchestration and privacy boundaries.

OCR worker and clipboard are mocked so no image or text escapes the tests.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.ocr_controller import OcrControllerMixin


class OcrControllerRefactorTests(unittest.TestCase):
    def test_main_window_preserves_original_ocr_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow,OcrControllerMixin))
        for name in (
            "ocr_history_clip", "ocr_last_screenshot", "start_ocr_file",
            "start_ocr", "ocr_recognized",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(ClipMintWindow,name),
                              getattr(OcrControllerMixin,name))

    def test_history_ocr_rejects_non_image_without_starting_worker(self):
        state=SimpleNamespace(
            store=SimpleNamespace(get=lambda _id: ("text",b"example")),
            start_ocr=Mock(),
        )
        OcrControllerMixin.ocr_history_clip(state,5)
        state.start_ocr.assert_not_called()

    def test_non_png_path_rejected_before_file_read(self):
        with TemporaryDirectory() as d:
            file=Path(d)/"bad.jpg"
            file.write_bytes(b"not a PNG")
            state=SimpleNamespace(start_ocr=Mock(),error=Mock())
            OcrControllerMixin.start_ocr_file(state,file)
            state.start_ocr.assert_not_called()
            state.error.assert_called_once()

    def test_oversized_or_empty_worker_input_rejected(self):
        state=SimpleNamespace(error=Mock())
        with patch("clipmint.ocr_controller.OcrWorker") as worker:
            OcrControllerMixin.start_ocr(state,b"")
            OcrControllerMixin.start_ocr(state,b"x"*(16*1024*1024+1))
            worker.assert_not_called()
        self.assertEqual(state.error.call_count,2)

    def test_sensitive_recognition_copies_without_retaining_history(self):
        state=SimpleNamespace(
            _own_clipboard_guard=SimpleNamespace(note_text=Mock()),
            store=SimpleNamespace(add=Mock()),
            refresh=Mock(),inform=Mock(),monitoring=True,history_security_error="",
        )
        with patch("clipmint.ocr_controller.QApplication") as app, \
             patch("clipmint.ocr_controller.sensitive_text",return_value=True):
            OcrControllerMixin.ocr_recognized(state,"password: dummy secret")
            app.clipboard.return_value.setText.assert_called_once()
        state._own_clipboard_guard.note_text.assert_called_once()
        state.store.add.assert_not_called()
        state.refresh.assert_not_called()

    def test_locked_history_cannot_store_ocr_plaintext(self):
        state=SimpleNamespace(
            _own_clipboard_guard=SimpleNamespace(note_text=Mock()),
            store=SimpleNamespace(add=Mock()),
            refresh=Mock(),inform=Mock(),monitoring=True,
            history_security_error="Keyring unavailable",
        )
        with patch("clipmint.ocr_controller.QApplication") as app, \
             patch("clipmint.ocr_controller.sensitive_text",return_value=False), \
             patch("clipmint.ocr_controller.looks_sensitive",return_value=False):
            OcrControllerMixin.ocr_recognized(state,"Ordinary test text")
            app.clipboard.return_value.setText.assert_called_once()
        state.store.add.assert_not_called()

    def test_safe_recognition_saves_exact_utf8_when_monitoring(self):
        data=b"Invoice number 735"
        state=SimpleNamespace(
            _own_clipboard_guard=SimpleNamespace(note_text=Mock()),
            store=SimpleNamespace(add=Mock()),
            refresh=Mock(),inform=Mock(),monitoring=True,
            history_security_error="",active_bin=lambda:"Work",
        )
        with patch("clipmint.ocr_controller.QApplication"), \
             patch("clipmint.ocr_controller.sensitive_text",return_value=False), \
             patch("clipmint.ocr_controller.looks_sensitive",return_value=False):
            OcrControllerMixin.ocr_recognized(state,data.decode())
        state.store.add.assert_called_once_with(
            "text",data,data.decode(),"Work",
            formats={"text/plain;charset=utf-8":data},
        )
        state.refresh.assert_called_once_with()

    def test_worker_starts_with_validated_language_and_signal_wiring(self):
        # A Mock supports signal.connect() and is hashable, matching
        # QObject worker identity in the live worker set.
        worker=Mock()
        state=SimpleNamespace(
            settings=SimpleNamespace(value=lambda *a,**k:"eng"),
            _ocr_workers=set(),
            ocr_recognized=Mock(),error=Mock(),
            statusBar=lambda:SimpleNamespace(showMessage=Mock()),
        )
        with patch("clipmint.ocr_controller.validate_language",
                   return_value="eng") as validate, \
             patch("clipmint.ocr_controller.OcrWorker",
                   return_value=worker) as cls:
            OcrControllerMixin.start_ocr(state,b"test png")
        validate.assert_called_once_with("eng")
        cls.assert_called_once_with(b"test png",state,language="eng")
        self.assertIn(worker,state._ocr_workers)
        worker.recognized.connect.assert_called_once()
        worker.failed.connect.assert_called_once()
        worker.finished.connect.assert_called_once()
        worker.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
