"""Local, bounded PNG readers for ClipMint's screenshot archive.

Images are read from the existing ~/Pictures/ClipMint directory.
Thumbnail decoding is scaled before QPixmap creation; no caches, uploads,
new files, external viewers or OCR requests are involved.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPen, QPixmap

MAX_PNG_BYTES = 40 * 1024 * 1024
MAX_IMAGE_DIMENSION = 18000
MAX_PIXELS = 80_000_000
THUMBNAIL_SIZE = QSize(190, 112)
PREVIEW_SIZE = QSize(1100, 760)


def read_screenshot(path: Path, bounds: QSize) -> tuple[QImage, QSize] | None:
    """Read a local screenshot at bounded display size; return true source dimensions."""
    try:
        if path.suffix.lower() != ".png" or not path.is_file():
            return None
        if path.stat().st_size > MAX_PNG_BYTES:
            return None
    except OSError:
        return None

    if bounds.width() <= 0 or bounds.height() <= 0:
        return None
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source_size = reader.size()
    if (not source_size.isValid()
            or source_size.width() > MAX_IMAGE_DIMENSION
            or source_size.height() > MAX_IMAGE_DIMENSION
            or source_size.width() * source_size.height() > MAX_PIXELS):
        return None
    # The provided bounds are a maximum, never a request to upscale.
    # Enlarging a small image for Copy image wastes memory and changes the
    # original image dimensions. Only scale down oversized previews.
    if source_size.width() > bounds.width() or source_size.height() > bounds.height():
        scaled_size = source_size.scaled(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(scaled_size)
    image = reader.read()
    if image.isNull():
        return None
    return image, source_size


def screenshot_thumbnail_icon(path: Path) -> QIcon | None:
    """Return a framed, aspect-preserving Qt icon for one PNG."""
    result = read_screenshot(path, THUMBNAIL_SIZE)
    if result is None:
        return None
    image, _ = result
    canvas = QPixmap(QSize(204, 126))
    canvas.fill(QColor("#1B131D"))
    painter = QPainter(canvas)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        preview = QPixmap.fromImage(image)
        x = (canvas.width() - preview.width()) // 2
        y = (canvas.height() - preview.height()) // 2
        painter.drawPixmap(x, y, preview)
        painter.setPen(QPen(QColor("#976578"), 1))
        painter.drawRect(0, 0, canvas.width() - 1, canvas.height() - 1)
    finally:
        painter.end()
    return QIcon(canvas)
