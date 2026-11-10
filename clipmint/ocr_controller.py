"""Offline OCR orchestration and privacy-aware clipboard result handling.

The Tesseract worker remains in ocr.py. This mixin preserves the existing
16 MiB PNG limit, worker lifecycle and secret-exclusion rules while allowing
the main window to remain responsible for state, history and notification UI.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from .clipboard_formats import sensitive_text
from .ocr import OcrWorker, validate_language
from .store import looks_sensitive


class OcrControllerMixin:
    """Image OCR entry points and result handling for ClipMintWindow."""

    def ocr_history_clip(self, clip_id: int):
        value = self.store.get(clip_id)
        if value is not None and value[0] == "image":
            self.start_ocr(value[1])

    def ocr_last_screenshot(self):
        if self._last_screenshot_path is not None:
            self.dismiss_screenshot_notice()
            self.start_ocr_file(self._last_screenshot_path)

    def start_ocr_file(self, path: Path):
        try:
            if (not path.is_file() or path.suffix.lower() != ".png"
                    or path.stat().st_size > 16 * 1024 * 1024):
                raise ValueError("Choose a PNG screenshot smaller than 16 MB")
            self.start_ocr(path.read_bytes())
        except (OSError, ValueError) as exc:
            self.error("OCR", str(exc))

    def start_ocr(self, png: bytes):
        if not png or len(png) > 16 * 1024 * 1024:
            self.error("OCR", "Choose a PNG image smaller than 16 MB")
            return
        try:
            language = validate_language(str(
                self.settings.value("ocr/language", "eng")
            ))
            worker = OcrWorker(png, self, language=language)
        except ValueError as exc:
            self.error("OCR", str(exc))
            return
        self._ocr_workers.add(worker)
        worker.recognized.connect(self.ocr_recognized)
        worker.failed.connect(lambda message: self.error("OCR", message))
        worker.finished.connect(lambda: self._ocr_workers.discard(worker))
        self.statusBar().showMessage("OCR: extracting text locally…", 6000)
        worker.start()

    def ocr_recognized(self, text: str):
        if not text.strip():
            self.inform("OCR", "No readable text detected")
            return
        self._own_clipboard_guard.note_text(text)
        QApplication.clipboard().setText(text)
        if (not sensitive_text(text) and not looks_sensitive(text)
                and self.monitoring and not self.history_security_error):
            data = text.encode("utf-8")
            self.store.add("text", data, " ".join(text.split())[:550],
                           self.active_bin(),
                           formats={"text/plain;charset=utf-8": data})
            self.refresh()
            self.inform("OCR complete", "Text copied and saved to clipboard history")
        else:
            self.inform("OCR complete", "Text copied; potential secrets excluded from history")

