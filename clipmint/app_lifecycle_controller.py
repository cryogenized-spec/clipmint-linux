"""Tray integration, window visibility, startup preference and explicit shutdown.

The QApplication runner still owns single-instance IPC. This mixin moves
existing callbacks without changing watcher lifetime, privacy cleanup or
recording refusal-on-quit behavior.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon,
)
from .autostart import (
    AutostartError, is_enabled as login_startup_enabled,
    set_enabled as set_login_startup,
)


class AppLifecycleMixin:
    """GUI lifecycle and tray callbacks for the main ClipMint window."""

    def set_login_startup_enabled(self, enabled: bool) -> None:
        try:
            set_login_startup(enabled)
        except (AutostartError, OSError) as exc:
            self.login_startup_toggle.blockSignals(True)
            self.login_startup_toggle.setChecked(login_startup_enabled())
            self.login_startup_toggle.blockSignals(False)
            self.error("Start at login", str(exc))

    def configure_tray(self):
        self.tray = None
        self.tray_stop = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self
        )
        menu = QMenu(self)
        menu.addAction("Show ClipMint").triggered.connect(self.show_window)
        menu.addAction("Quick search popup").triggered.connect(self.toggle_quick_popup)
        menu.addSeparator()
        menu.addAction("Screenshot full screen").triggered.connect(self.screenshot_full)
        menu.addAction("Screenshot selected area").triggered.connect(self.choose_screenshot)
        menu.addAction("Record MP4").triggered.connect(lambda: self.choose_recording("MP4"))
        menu.addAction("Record GIF").triggered.connect(lambda: self.choose_recording("GIF"))
        self.tray_stop = menu.addAction("Stop recording")
        self.tray_stop.triggered.connect(self.stop_recording)
        menu.addSeparator()
        menu.addAction("Quit ClipMint").triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.tray_notification_clicked)
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger and self.recorder_window is None:
            self.show_window()

    def show_window(self):
        if not self.isVisible():
            # Last-chance recovery if the desktop skipped a clipboard signal
            # while the archive was hidden. This can only retrieve the current
            # item, not every intermediate copy made while ClipMint was quit.
            self.poll_hidden_clipboard()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_notification_clicked(self):
        if self._last_tray_notification == "screenshot":
            self.edit_last_screenshot()

    def inform(self, title: str, message: str):
        self._last_tray_notification = None
        self.statusBar().showMessage(f"{title}: {message}", 7000)
        if self.tray is not None:
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def error(self, title: str, message: str):
        self.statusBar().showMessage(message, 10000)
        QMessageBox.warning(self.recorder_window or self, title, message)

    def closeEvent(self, event):
        self.lock_vault()
        if self._closing:
            event.accept()
            return
        # The X button closes the interface, not the clipboard watcher.
        # System tray availability is not reliable on every Cinnamon panel.
        # The single-instance socket makes the hidden window reachable again
        # through the normal launcher, including on desktops without a tray.
        self.hide()
        event.ignore()

    def quit_app(self):
        if getattr(self, "_quit_pending", False) or getattr(self, "_quit_complete", False):
            return
        if self.recorder.process is not None:
            self.error("Recording active", "Finish recording before quitting")
            return
        # QThread must not be destroyed with its parent QWidget while running.
        # Allow offline OCR to finish (bounded by Tesseract's timeout), but
        # suppress any late OCR result once shutdown has been requested.
        if any(worker.isRunning() for worker in getattr(self, "_ocr_workers", ())):
            self._closing = True
            self._quit_pending = True
            self.statusBar().showMessage("Finishing OCR before quitting ClipMint…")
            return
        AppLifecycleMixin._finish_quit(self)

    def _finish_quit(self):
        if getattr(self, "_quit_complete", False):
            return
        if self.recorder.process is not None:
            self.error("Recording active", "Finish recording before quitting")
            return
        if self.recorder_window is not None:
            self.recorder_window.hide()
            self.recorder_window.deleteLater()
            self.recorder_window = None
        self._closing = True
        self._quit_pending = False
        runtime = getattr(self, "_runtime_timers", None)
        if runtime is None:
            # Standalone integration tests and pre-registration startup paths.
            self._auto_update_timer.stop()
            self._hidden_clipboard_timer.stop()
        else:
            runtime.stop_all()
        self.lock_vault()
        self.clear_temporary_on_normal_exit()
        self.store.close()
        if self.tray is not None:
            self.tray.hide()
        # The Qt server owns the advisory lock, not the window lifetime.
        instance = getattr(self, "_instance_server", None)
        if instance is not None:
            instance.close()
        self._quit_complete = True
        QApplication.quit()
