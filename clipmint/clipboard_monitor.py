"""Clipboard monitor: privacy-aware X11 change handling and recovery.

The main window owns the store, clipboard guards, timers and monitoring state.
Keep signal names and all privacy/auto-sort protections unchanged.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from .clipboard_formats import from_mime, is_concealed, sensitive_text
from .foreground_privacy import blocked_foreground, DEFAULT_BLOCKED


class ClipboardMonitorMixin:
    """Signal callbacks, missed-event polling, expiry and pause/resume."""

    def _clipboard_generation_changed(self):
        """Track *all* X11 clipboard writes, including Vault and concealed data."""
        self._sensitive_clipboard_token += 1

    def poll_hidden_clipboard(self):
        """Recover the latest plain-text copy when X11 omits dataChanged.

        Paused/locked monitoring must never capture a clipboard value later
        when the user resumes. No clipboard contents or source titles are
        retained beyond the in-memory digest.
        """
        if self._closing or getattr(self.store, "closed", False):
            return
        if self.isVisible():
            return
        data = QApplication.clipboard().mimeData()
        changed = self._hidden_text_probe.observe(data)
        if changed and self.monitoring and not self.history_security_error:
            self.clipboard_changed()

    def clipboard_changed(self):
        # Clear our own-write expectation on every event, even while history
        # is paused; never carry a stale skip across Pause/Resume.
        data = QApplication.clipboard().mimeData()
        self._hidden_text_probe.observe(data)
        if self._own_clipboard_guard.consume(data):
            return
        if (not self.monitoring or self._closing
                or getattr(self.store, "closed", False) or data is None):
            return
        if is_concealed(data):
            self._privacy_skipped += 1
            self.statusBar().showMessage("Concealed clipboard item excluded")
            return
        if (data.hasText() and self._vault_clipboard_text is not None
                and data.text() == self._vault_clipboard_text):
            return
        if blocked_foreground(str(self.settings.value(
                "privacy/blocked_foreground", ", ".join(DEFAULT_BLOCKED)
        ))):
            self._privacy_skipped += 1
            return
        png = None
        if data.hasImage():
            picture = QApplication.clipboard().image()
            if not picture.isNull():
                buffer_bytes = QByteArray()
                buffer = QBuffer(buffer_bytes)
                if buffer.open(QIODevice.OpenModeFlag.WriteOnly):
                    saved = picture.save(buffer, "PNG")
                    buffer.close()
                    if saved:
                        png = bytes(buffer_bytes)
        entry = from_mime(data, png=png)
        if entry is None:
            # Preserve a generic privacy notice. Expire plaintext secrets
            # only when the clipboard still contains the very same string.
            if data.hasText() and sensitive_text(data.text()):
                original = data.text()
                token = self._sensitive_clipboard_token
                QTimer.singleShot(
                    30000,
                    lambda: self.expire_sensitive_clipboard(token, original),
                )
                self.statusBar().showMessage(
                    "Sensitive clipboard content not saved · clears after "
                    "30 seconds if unchanged", 5500,
                )
            elif is_concealed(data):
                self.statusBar().showMessage(
                    "Sensitive clipboard content detected · not saved to history", 6000
                )
            return
        title = entry.preview
        if entry.kind == "image" and png:
            image = QImage.fromData(png, "PNG")
            title = f"Image {image.width()} × {image.height()}"
        result = self._clip_ingestion.ingest(
            entry, self.active_bin(),
            autosort_enabled=self.autosort_enabled, preview=title,
        )
        if result.excluded_by_rule:
            self.statusBar().showMessage("Clip excluded by Autosort rule", 4000)
            return
        self.refresh()
        if (result.saved_id is not None and self.view_bin() is not None
                and result.destination != self.view_bin()):
            self.statusBar().showMessage(
                f"Clip saved in {result.destination}. Choose All collections to see it.",
                6500,
            )

    def expire_sensitive_clipboard(self, token: int, expected: str) -> None:
        """Never clear unrelated clipboard content copied in the meantime."""
        if token != self._sensitive_clipboard_token:
            return
        clipboard = QApplication.clipboard()
        if clipboard.text() == expected:
            clipboard.clear()

    def toggle_monitoring(self):
        if self.history_security_error:
            self.error("Clipboard privacy", "Unlock the desktop keyring and restart ClipMint")
            return
        if not self.monitoring:
            # A pause may end before the next hidden poll. Baseline the
            # CURRENT system clipboard now, so nothing copied during pause
            # can be ingested merely because monitoring was resumed.
            self._hidden_text_probe.observe(QApplication.clipboard().mimeData())
        self.monitoring = not self.monitoring
        self.pause_button.setText("Pause monitoring" if self.monitoring else "Resume monitoring")
        self.refresh()
        self.inform("Clipboard monitoring", "Enabled" if self.monitoring else "Paused")

