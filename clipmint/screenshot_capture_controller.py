"""Screenshot selection, capture notifications and saved-image actions.

This controller only moves the existing Qt callbacks. It keeps successful
capture background-only, preserves cancellation restoration and clipboard
image copy, and does not change recording or persistence engines.
"""
from __future__ import annotations

from pathlib import Path
import subprocess

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .capture import AreaSelector, screenshots_dir, stamped_filename
from .screenshot_editor import open_image_editor
from .screenshot_notice import play_capture_sound


class ScreenshotCaptureControllerMixin:
    """Screen-region selection and screenshot lifecycle callbacks."""

    def select_area(self, purpose: str):
        if self.selector is not None or self.recorder_window is not None:
            return
        if purpose == "video" and self.recorder.process is not None:
            self.inform("Recording", "Finish the current recording first")
            return
        # Only return to ClipMint if the user was working in its foreground
        # window. Global Cinnamon grabs must not summon it over Firefox.
        self._capture_restore_main = self.isVisible() and self.isActiveWindow()
        # The main window AND the screenshot notice can appear in a capture
        # unless the compositor has had time to hide a previously visible UI.
        had_visible_window = self.isVisible() or (
            self.screenshot_notice is not None
            and self.screenshot_notice.isVisible()
        )
        if self.screenshot_notice is not None:
            self.screenshot_notice.hide()
        # An already hidden UI needs no compositor settling delay.
        self.hide()
        QTimer.singleShot(
            250 if had_visible_window else 0,
            lambda: self.begin_selection(purpose),
        )

    def begin_selection(self, purpose):
        try:
            self.selector = AreaSelector(purpose)
        except Exception as exc:
            if self._capture_restore_main:
                self.show_window()
            self._capture_restore_main = False
            self.error("Screen capture", str(exc))
            return
        self.selector.cancelled.connect(self.selection_cancelled)
        if purpose == "image":
            self.selector.selected.connect(self.save_screenshot)
        else:
            self.selector.selected.connect(self.start_video)

    def clear_selection(self):
        self.selector = None

    def selection_cancelled(self):
        QTimer.singleShot(0, self.clear_selection)
        if self._capture_restore_main:
            self.show_window()
        self._capture_restore_main = False

    def choose_screenshot(self):
        self.select_area("image")

    def screenshot_full(self):
        if self.selector is not None or self.recorder.active:
            return
        self._capture_restore_main = self.isVisible() and self.isActiveWindow()
        if self.screenshot_notice is not None:
            self.screenshot_notice.hide()
        self.hide()
        QTimer.singleShot(350, self.finish_full_screenshot)

    def finish_full_screenshot(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            if self._capture_restore_main:
                self.show_window()
            self._capture_restore_main = False
            self.error("Screenshot", "No screen detected")
            return
        self.save_screenshot(None, screen.grabWindow(0))

    def save_screenshot(self, _rect, pixmap):
        QTimer.singleShot(0, self.clear_selection)
        path = screenshots_dir() / stamped_filename("screenshot", "png")
        if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
            if self._capture_restore_main:
                self.show_window()
            self._capture_restore_main = False
            self.error("Screenshot", "Could not save screenshot")
            return
        # Make the pixels immediately pasteable into Firefox / another app.
        # Clipboard history may also record the image as an ordinary clip.
        # Defensive: successful capture is always a background operation.
        # Keep the archive hidden even when a future caller bypasses the
        # ordinary region-selection path that already hides the window.
        self.hide()
        QApplication.clipboard().setImage(pixmap.toImage())
        # Successful screenshots must NEVER summon the main app, even when
        # launched from a button in the previously active ClipMint window.
        # The selection widget was closed and the main app was hidden before
        # sampling the screen. User actions live in the small independent
        # screenshot notice; Ctrl+V works without choosing one.
        self._capture_restore_main = False
        self.notify_screenshot_captured(path)
        # Update the archive without switching to or raising the main window.
        self.refresh_library("Screenshots", select_path=path)

    def notify_screenshot_captured(self, path: Path):
        """Notify only after a PNG was saved successfully to disk."""
        self._last_screenshot_path = Path(path)
        self._screenshot_notice_token += 1
        token = self._screenshot_notice_token
        self.statusBar().showMessage(f"Screenshot captured: {path}", 8000)
        if self.screenshot_notice is not None:
            self.screenshot_notice.present()
            QTimer.singleShot(
                10000, lambda: self.dismiss_screenshot_notice(token)
            )
        # Do not duplicate the two-action popup with a tray balloon.
        # The standard Cinnamon shutter event is best-effort, never blocking.
        if self.settings.value("capture/sound_enabled", True, type=bool):
            play_capture_sound()

    def dismiss_screenshot_notice(self, token=None):
        if type(token) is int and token != self._screenshot_notice_token:
            return
        if self.screenshot_notice is not None:
            self.screenshot_notice.hide()

    def edit_last_screenshot(self, *_args):
        """A notification click must never create a new screenshot."""
        path = self._last_screenshot_path
        if path is None:
            return
        preference = str(self.settings.value("capture/editor", "auto"))
        try:
            application, editor = open_image_editor(path, preference)
        except (OSError, ValueError) as exc:
            self.error(
                "Screenshot editor",
                f"Could not open the captured PNG: {exc}. "
                "Choose an installed editor in Settings.",
            )
            return
        self.dismiss_screenshot_notice()
        if editor:
            self.statusBar().showMessage(
                f"Opening screenshot in {application}", 5000
            )
        else:
            self.statusBar().showMessage(
                "Opening screenshot with the system image application; "
                "it may be a viewer. Select an editor in Settings.", 8000
            )

    def open_path(self, path: Path):
        try:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.error("Open", str(exc))

    def open_folder(self, folder: Path):
        self.open_path(folder)

