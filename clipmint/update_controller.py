"""Verified-preview update UI and worker orchestration.

The network and package-integrity implementation remains in updater.py.
This controller retains explicit full-installer consent, opt-in automatic
explicit download consent, disabled background staging, and UI-thread signals.
"""
from __future__ import annotations

from pathlib import Path
import threading
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon

from .updater import (
    check_for_preview_update, download_verified_preview,
    PreviewUpdate,
)


class UpdateSignals(QObject):
    finished = Signal(object, str, str)


class UpdateControllerMixin:
    def set_auto_updates_enabled(self, enabled: bool):
        self.settings.setValue("updates/automatic", bool(enabled))
        if enabled:
            self.check_for_updates(manual=False)

    def _auto_check_updates(self):
        if not self.settings.value("updates/automatic", False, type=bool):
            return
        last = int(self.settings.value("updates/last_checked", 0, type=int))
        if int(time.time()) - last < 24 * 60 * 60:
            return
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual: bool = False):
        """Check preview availability; never download anything in background."""
        if self._update_busy or self._closing:
            return
        self._update_busy = True
        self._available_update = None
        self.download_update_button.setEnabled(False)
        self.check_update_button.setEnabled(False)
        self.update_status.setText("Checking official ClipMint previews…")
        # RELEASE SECURITY GATE (#63): checks only. The old saved opt-in
        # preference now authorizes notification checks, never downloads.
        # SHA-256 files co-hosted with assets do not authenticate a publisher.
        # Restore staging only after independently signed release manifests
        # and fail-closed signature/rollback tests are deployed.
        signals = self._update_signals

        def check_worker():
            candidate = None
            downloaded = ""
            error = ""
            try:
                candidate = check_for_preview_update()
                # Even for a previously enabled updates/automatic preference,
                # do not stage unsigned preview packages without consent.
            except Exception as exc:
                error = str(exc) or type(exc).__name__
            try:
                signals.finished.emit(candidate, downloaded, error)
            except RuntimeError:
                pass

        threading.Thread(
            target=check_worker, name="ClipMint-update-check", daemon=True
        ).start()

    def download_available_preview(self):
        """Explicit approval before any possible full-installer transfer."""
        candidate = self._available_update
        if self._update_busy or self._closing or candidate is None:
            return
        size_mb = candidate.package_size / (1024 * 1024)
        reply = QMessageBox.question(
            self, "Approve ClipMint preview download?",
            f"ClipMint {candidate.version} may require downloading a full "
            f"{size_mb:.1f} MiB installer. A smaller verified patch will be "
            "tried first if available, but may fall back to the full package.\n\n"
            "Checksums detect corruption, but do not independently prove "
            "publisher identity. This is an explicitly approved network-data "
            "download, NOT an automatic update. Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._update_busy = True
        self.check_update_button.setEnabled(False)
        self.download_update_button.setEnabled(False)
        self.update_status.setText("Downloading approved verified preview…")
        signals = self._update_signals

        def download_worker():
            path, error = "", ""
            try:
                path = str(download_verified_preview(candidate))
            except Exception as exc:
                error = str(exc) or type(exc).__name__
            try:
                signals.finished.emit(candidate, path, error)
            except RuntimeError:
                pass

        threading.Thread(
            target=download_worker, name="ClipMint-preview-download", daemon=True
        ).start()

    def _on_update_result(
        self, candidate: PreviewUpdate | str | None, downloaded: str, error: str
    ):
        self._update_busy = False
        self.check_update_button.setEnabled(True)
        self.settings.setValue("updates/last_checked", int(time.time()))
        self._available_update = (
            candidate if isinstance(candidate, PreviewUpdate) else None
        )
        self.download_update_button.setEnabled(
            self._available_update is not None and not downloaded
        )
        version = (
            candidate.version if isinstance(candidate, PreviewUpdate)
            else (candidate or "")
        )
        if error:
            self.update_status.setText("Update check/download failed: " + error)
            return
        if not version:
            self.update_status.setText(
                "ClipMint is up to date for the verified preview channel."
            )
            return
        if downloaded:
            self._verified_update_path = Path(downloaded)
            self.install_update_button.setEnabled(True)
            self.update_status.setText(
                f"Verified update {version} downloaded. "
                "Open the installer to approve installation."
            )
            if self.tray is not None:
                self.tray.showMessage(
                    "ClipMint update ready",
                    "Verified preview downloaded; approve install in Settings.",
                    QSystemTrayIcon.MessageIcon.Information, 4000,
                )
        elif self._available_update is not None:
            size_mb = self._available_update.package_size / (1024 * 1024)
            self.update_status.setText(
                f"New preview {version} available. Background checks never "
                f"download packages. Full installer: {size_mb:.1f} MiB. "
                "Nothing was downloaded. Choose Download to approve a "
                "patch or installer; checksum verification is not a "
                "publisher signature."
            )
        else:
            self.update_status.setText(
                f"New ClipMint preview {version} is available."
            )

    def open_verified_update(self):
        path = self._verified_update_path
        if path is None or not path.is_file() or path.is_symlink():
            self.install_update_button.setEnabled(False)
            self.update_status.setText(
                "Downloaded package missing; please check again."
            )
            return
        # The native Mint package installer handles authorization. Never
        # invoke sudo or download-and-execute silently.
        self.open_path(path)

