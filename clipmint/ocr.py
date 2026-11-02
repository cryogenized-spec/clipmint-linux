"""Offline OCR for PNG image clipboard entries (Tesseract, no cloud upload).

Runs off the UI thread. PNG is supplied on stdin; no image is written to a
temporary directory. Keep the result bounded to avoid accidental huge clips.
"""
from __future__ import annotations
import shutil
import subprocess
from PySide6.QtCore import QThread, Signal

MAX_IMAGE = 16 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024


def extract_text(png: bytes, executable: str | None = None) -> str:
    if not png or len(png) > MAX_IMAGE or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Please select a valid PNG image smaller than 16 MB")
    binary = executable or shutil.which("tesseract")
    if not binary:
        raise RuntimeError("OCR requires Tesseract. Install tesseract-ocr and tesseract-ocr-eng.")
    try:
        proc = subprocess.run(
            [binary, "stdin", "stdout", "-l", "eng"],
            input=png, capture_output=True, timeout=35, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Text recognition timed out") from exc
    if proc.returncode:
        # Don't log external image text or unbounded tool output.
        raise RuntimeError("Tesseract could not read this image")
    if len(proc.stdout) > MAX_TEXT:
        raise RuntimeError("Recognized text exceeds the 2 MB clipboard limit")
    return proc.stdout.decode("utf-8", errors="replace").strip()


class OcrWorker(QThread):
    recognized = Signal(str)
    failed = Signal(str)

    def __init__(self, png: bytes, parent=None):
        super().__init__(parent)
        self.png = png

    def run(self):
        try:
            text = extract_text(self.png)
        except (RuntimeError, ValueError, OSError) as exc:
            self.failed.emit(str(exc))
        else:
            self.recognized.emit(text)
        finally:
            self.png = b""
