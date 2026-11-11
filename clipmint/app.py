"""ClipMint Linux application coordinator; feature logic lives in focused modules."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer, QSettings
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from .branding import ChromaticWordmark, register_display_font
from .crimson_ui import build_crimson_ui
from .capture import AreaSelector, RegionRecorder
from .recording_ui import RecorderWindow
from .store import ClipStore
from .smart_types import DEFAULT_BINS as SMART_BINS
from .vault import Vault
from .screenshot_notice import ScreenshotNotice
from .clipboard_guard import OwnClipboardGuard, HiddenTextClipboardProbe
from .quick_popup import QuickPopup
from .productivity import PasteQueue
from .updater import PreviewUpdate
from .update_controller import UpdateControllerMixin, UpdateSignals
from .recording_controller import RecordingControllerMixin
from .vault_controller import VaultControllerMixin
from .autosort_controller import AutosortControllerMixin
from .history_controller import HistoryControllerMixin
from .library_controller import LibraryControllerMixin, ImagePreviewLabel
from .hotkey_popup_controller import HotkeyPopupControllerMixin
from .clipboard_monitor import ClipboardMonitorMixin
from .history_maintenance_controller import HistoryMaintenanceMixin
from .history_security_controller import HistorySecurityControllerMixin
from .screenshot_capture_controller import ScreenshotCaptureControllerMixin
from .app_lifecycle_controller import AppLifecycleMixin
from .ocr_controller import OcrControllerMixin
from .settings_controller import SettingsControllerMixin, SHORTCUT_SPECS, WheelSafeHistoryLimitComboBox
from .single_instance import InstanceServer, send_command
from .clipboard_page import build_clipboard_page as compose_clipboard_page, build_info_page as compose_info_page
from .vault_page import build_vault_page as compose_vault_page
from .window_layout import update_manga_visibility as apply_manga_layout
from .window_theme import THEME
from . import window_actions


class ClipMintWindow(OcrControllerMixin, AppLifecycleMixin, ScreenshotCaptureControllerMixin, HistorySecurityControllerMixin, HistoryMaintenanceMixin, ClipboardMonitorMixin, HotkeyPopupControllerMixin, LibraryControllerMixin, SettingsControllerMixin, HistoryControllerMixin, UpdateControllerMixin, AutosortControllerMixin, VaultControllerMixin, RecordingControllerMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipMint · Clipboard & Capture")
        self.brand_family = register_display_font()
        self.resize(1300, 870)
        self.setMinimumSize(850, 600)
        self.store = ClipStore()
        self.settings = QSettings("ClipMint", "ClipMint")
        self._temporary_exit_cleaned = False
        self._update_busy = False
        self._verified_update_path = None
        self._available_update: PreviewUpdate | None = None
        self._update_signals = UpdateSignals(self)
        self._update_signals.finished.connect(self._on_update_result)
        self._auto_update_timer = QTimer(self)
        self._auto_update_timer.setInterval(6 * 60 * 60 * 1000)
        self._auto_update_timer.timeout.connect(self._auto_check_updates)
        self._temporary_expiry_timer = QTimer(self)
        self._temporary_expiry_timer.setInterval(5 * 60 * 1000)
        self._temporary_expiry_timer.timeout.connect(self.expire_temporary_if_enabled)
        self._initialize_encrypted_history()
        history_mb = self.settings.value("history/max_total_mb", 0, type=int)
        self.store.max_total_bytes = (
            history_mb * 1024 * 1024
            if history_mb in (128, 256, 512, 1024) else None
        )
        # Seed new installations with ready-to-use Smart collections, but do
        # not alter existing rule sets or overwrite a deliberate disabled state.
        if (not self.history_security_error
                and not self.settings.contains("autosort/rules")):
            for name in SMART_BINS:
                if name not in self.store.bins():
                    self.store.add_bin(name)
        self.vault = Vault()
        self._vault_clipboard_text = None
        self._vault_clipboard_token = 0
        self._sensitive_clipboard_token = 0
        self._vault_lock_timer = QTimer(self)
        self._vault_lock_timer.setSingleShot(True)
        self._vault_lock_timer.timeout.connect(self.lock_vault)
        self.recorder = RegionRecorder()
        # Decryption is deliberately synchronous and ephemeral. Debounce
        # rapid text edits to avoid decrypting up to 1,000 rows per keystroke.
        self._history_search_timer = QTimer(self)
        self._history_search_timer.setSingleShot(True)
        self._history_search_timer.setInterval(180)
        self._history_search_timer.timeout.connect(self.refresh)
        self.monitoring = not bool(self.history_security_error)
        self.selector: AreaSelector | None = None
        self.recorder_window: RecorderWindow | None = None
        self.capture_rect = None
        self.capture_scale = None
        self.capture_origin = None
        self.capture_format = "MP4"
        self._privacy_skipped = 0
        self._closing = False
        self._own_clipboard_guard = OwnClipboardGuard()
        self._hidden_text_probe = HiddenTextClipboardProbe()
        self._hidden_clipboard_timer = QTimer(self)
        self._hidden_clipboard_timer.setInterval(1500)
        self._hidden_clipboard_timer.timeout.connect(self.poll_hidden_clipboard)
        self._last_screenshot_path = None
        self._capture_restore_main = False
        self._screenshot_thumbnail_generation = 0
        self._ocr_workers = set()
        self._last_tray_notification = None
        self._screenshot_notice_token = 0
        self.screenshot_notice = None

        # Native reconstruction of the approved Crimson Archive v2 prototype.
        # All content comes from the existing history store and capture methods.
        self.paste_queue = PasteQueue()
        self.wordmark = ChromaticWordmark(self.brand_family)
        build_crimson_ui(self, ImagePreviewLabel)
        self.build_library_page("Screenshots")
        self.build_library_page("Recordings")
        self.build_vault_page()
        self.build_autosort_page()
        self.build_settings_page()
        self.install_shortcuts()
        self.quick_popup = QuickPopup(self.store, self.quick_pick)
        self.statusBar().showMessage(
            self.history_security_error or self.history_integrity_warning or
            "Ready · Left-click to preview, right-click for Copy / Pin / Move / Delete"
        )
        self.configure_tray()
        self.screenshot_notice = ScreenshotNotice(
            self, self.edit_last_screenshot, self.dismiss_screenshot_notice,
            on_ocr=self.ocr_last_screenshot,
        )
        # Every clipboard replacement invalidates earlier sensitive expiry
        # deadlines, even when history monitoring skips or suppresses a copy.
        QApplication.clipboard().dataChanged.connect(
            self._clipboard_generation_changed
        )
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        # Starting the watcher must not retroactively import text copied
        # while ClipMint was explicitly QUIT. Observe the current clipboard
        # as a baseline, then capture future changes through dataChanged
        # and the hidden-window recovery timer.
        self._hidden_text_probe.observe(QApplication.clipboard().mimeData())
        # Keep observing the most recent plain-text clip after the archive is
        # closed, even if a Cinnamon/X11 clipboard manager misses a signal.
        # This is a fallback for a LIVE hidden process, not a background
        # service that can run after the user explicitly chooses Quit.
        self._hidden_clipboard_timer.start()
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.poll_recording)
        self.poller.start(300)
        self.open_section(0)
        self._update_manga_visibility()
        self.update_temporary_expiry_schedule()
        # Only an explicitly saved enabled setting can trigger cleanup on
        # startup. An upgrade or an application crash cannot opt users in.
        if self._temporary_expiry_timer.isActive():
            QTimer.singleShot(0, self.expire_temporary_if_enabled)
        # Do not call clipboard_changed() unconditionally at startup: it
        # would save a clip from a period in which monitoring was not active.
        QTimer.singleShot(900, self.offer_pending_recordings)
        if getattr(sys, "frozen", False):
            # Network activity is explicitly configurable and never runs in
            # the Qt UI thread. Development/testing checkouts remain offline
            # unless the user presses Check now.
            self._auto_update_timer.start()
            QTimer.singleShot(12000, self._auto_check_updates)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "manga_dock"):
            self._update_manga_visibility()

    def _update_manga_visibility(self):
        return apply_manga_layout(self)

    def build_clipboard_page(self):
        return compose_clipboard_page(self)

    def build_info_page(self, title: str, description: str):
        return compose_info_page(self, title, description)

    def build_vault_page(self):
        return compose_vault_page(self)

    def view_bin(self) -> str | None:
        return window_actions.view_bin(self)

    def active_bin(self) -> str:
        return window_actions.active_bin(self)

    def new_bin(self):
        return window_actions.new_bin(self)

    def open_section(self, index: int):
        return window_actions.open_section(self, index)

    def _schedule_history_search(self, *_args):
        return window_actions._schedule_history_search(self, *_args)

    def copy_selected(self):
        return window_actions.copy_selected(self)

    def copy_clip(self, item):
        return window_actions.copy_clip(self, item)

def main():
    if sys.platform != "linux":
        raise SystemExit("ClipMint currently supports Linux only")
    arguments = sys.argv[1:]
    capture = ("screenshot-area" if "--screenshot-area" in arguments else
               "record-area" if "--record-area" in arguments else None)
    hidden = "--hidden" in arguments and not (
        capture or "--toggle" in arguments or "--quit" in arguments
    )
    command = (capture if capture else
               "toggle" if "--toggle" in arguments else
               "quit" if "--quit" in arguments else
               "ping" if hidden else "show")
    # Every invocation first signals an existing instance. The running daemon
    # owns the clipboard; --toggle never starts a second clipboard watcher.
    app = QApplication([sys.argv[0]])
    app.setApplicationName("ClipMint")
    # The Qt event loop and clipboard signals must remain alive after *all*
    # windows are hidden. Only explicit Quit/--quit ends the watcher.
    app.setQuitOnLastWindowClosed(False)
    if send_command(command):
        return
    if command == "quit":
        return
    if os.environ.get("XDG_SESSION_TYPE", "x11").lower() != "x11":
        QMessageBox.warning(None, "X11 required",
                            "ClipMint currently requires an X11 session (e.g. Cinnamon X11).")
        raise SystemExit(1)
    window = ClipMintWindow()
    def on_command(action):
        if action == "toggle":
            window.toggle_quick_popup()
        elif action == "show":
            window.show_window()
        elif action == "screenshot-area":
            QTimer.singleShot(0, window.choose_screenshot)
        elif action == "record-area":
            QTimer.singleShot(0, lambda: window.choose_recording("MP4"))
        elif action == "quit":
            window.quit_app()
    try:
        window._instance_server = InstanceServer(
            on_command, window, occupied_command="ping" if hidden else "show"
        )
    except RuntimeError as exc:
        QMessageBox.warning(None, "ClipMint", str(exc))
        return
    if command == "toggle":
        QTimer.singleShot(150, window.toggle_quick_popup)
    elif command == "screenshot-area":
        # A cold-start global screenshot key must not reveal the main window.
        QTimer.singleShot(0, window.choose_screenshot)
    elif command == "record-area":
        window.show()
        QTimer.singleShot(150, lambda: window.choose_recording("MP4"))
    elif hidden:
        # Login startup runs headlessly regardless of the desktop's tray
        # support. Reopen through the app launcher (single-instance 'show').
        pass
    else:
        window.show()
    raise SystemExit(app.exec())
