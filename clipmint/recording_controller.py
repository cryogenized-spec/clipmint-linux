"""Recording UI controller for ClipMint's main Qt window.

This mixin owns the recorder popup, recovery choices and start/stop/finalize
transitions. All existing window fields, signals and user-facing callbacks are
kept intact; Qt widget ownership stays with ClipMintWindow. The mixin requires
no separate QObject and does not alter the capture or background watcher path.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QMessageBox

from .capture import RegionRecorder
from .recording_ui import RecorderWindow, SaveClipDialog
from .recording_recovery import pending_recordings, resolve_pending


class RecordingControllerMixin:
    def offer_pending_recordings(self):
        """Offer recovery on startup; never delete a crashed recording silently."""
        if self._closing or self.recorder.process is not None:
            return
        unfinished = pending_recordings()
        if not unfinished:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("ClipMint · Unfinished recordings")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(f"Found {len(unfinished)} unfinished recording(s) from an earlier session.")
        dialog.setInformativeText(
            "Recover will preserve these files under visible 'recovered-' names; "
            "an interrupted MP4 may be unplayable. Discard deletes the files "
            "and their FFmpeg logs. Keep for later changes nothing."
        )
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
        dialog.button(QMessageBox.StandardButton.Yes).setText("Recover files")
        dialog.button(QMessageBox.StandardButton.No).setText("Discard files")
        dialog.button(QMessageBox.StandardButton.Cancel).setText("Keep for later")
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        action = dialog.exec()
        if action == int(QMessageBox.StandardButton.Cancel):
            return
        choice = ("recover" if action == int(QMessageBox.StandardButton.Yes)
                  else "discard" if action == int(QMessageBox.StandardButton.No)
                  else None)
        if choice is None:
            return
        completed, errors = 0, []
        for path in unfinished:
            try:
                resolve_pending(path, choice)
                completed += 1
            except (OSError, ValueError) as exc:
                errors.append(f"{path.name}: {exc}")
        self.refresh_library("Recordings")
        if errors:
            QMessageBox.warning(
                self, "Recording recovery incomplete",
                f"Processed {completed} of {len(unfinished)} files. "
                "Files that could not be processed were preserved.\n"
                + "\n".join(errors[:3]),
            )
        else:
            self.inform("Recording recovery",
                        f"{completed} recording(s) recovered" if choice == "recover"
                        else f"{completed} unfinished recording(s) discarded")

    def choose_recording(self, file_format: str = "MP4"):
        self.capture_format = file_format if file_format in ("MP4", "GIF") else "MP4"
        self.select_area("video")

    def start_video(self, rect, _pixmap):
        # Retain the selection's actual screenshot-to-logical pixel ratio so
        # FFmpeg records exactly the same area shown by the selection overlay.
        self.capture_scale = self.selector.pixel_scale if self.selector else None
        self.capture_origin = self.selector.screen_rect.topLeft() if self.selector else None
        QTimer.singleShot(0, self.clear_selection)
        self.capture_rect = rect
        # Main ClipMint remains hidden, and the selection overlay has exited.
        QTimer.singleShot(300, self.show_recorder)

    def show_recorder(self):
        self.recorder_window = RecorderWindow(self.capture_rect, self.capture_format)
        self.recorder_window.start_requested.connect(self.launch_recorder)
        self.recorder_window.stop_requested.connect(self.stop_recording)
        self.recorder_window.cancelled.connect(self.cancel_recorder)
        self.recorder_window.place_outside()
        self.update_buttons()

    def cancel_recorder(self):
        if self.recorder.process is None:
            # Cancelling before Start releases the recorder session; otherwise
            # the main window's Record controls remain disabled indefinitely.
            self.recorder_window = None
            self.update_buttons()
            self.show_window()

    def launch_recorder(self, quality: str, file_format: str):
        try:
            path = self.recorder.start(
                self.capture_rect, quality, file_format,
                pixel_scale=self.capture_scale,
                screen_origin=self.capture_origin,
            )
        except Exception as exc:
            if self.recorder_window:
                self.recorder_window.start_failed()
            self.error("Recording", str(exc))
            return
        if self.recorder_window:
            self.recorder_window.recording_started(path, self.recorder.estimated_bytes_per_second)
        self.update_buttons()

    def stop_recording(self):
        if self.recorder.stop():
            self.statusBar().showMessage("Finalizing recording; please keep ClipMint open")
        elif self.recorder.process is None:
            self.inform("Recording", "No active recording")
        self.update_buttons()

    def poll_recording(self):
        result = self.recorder.finished()
        if result is None:
            return
        status, path = result
        recorder_window = self.recorder_window
        duration = recorder_window.timer_label.text() if recorder_window else "00:00:00"
        if recorder_window is not None:
            recorder_window.recording_finished()
            recorder_window.deleteLater()
            self.recorder_window = None
        self.update_buttons()
        if status == 0 and path and path.exists() and path.stat().st_size:
            dialog = SaveClipDialog(path, duration, self.recorder.quality)
            save = dialog.exec() == QDialog.DialogCode.Accepted
            try:
                result_path = RegionRecorder.resolve(path, save)
                if result_path:
                    self.inform("Recording saved", str(result_path))
                else:
                    self.inform("Recording discarded", "Temporary clip deleted")
            except OSError as exc:
                self.error("Recording file", str(exc))
        else:
            self.error("Recording error", "FFmpeg failed; check the .ffmpeg.log in Videos/ClipMint")
        self.show_window()
        self.refresh_library("Recordings")

    def update_buttons(self):
        busy = self.recorder.process is not None or self.recorder_window is not None
        self.record_button.setEnabled(not busy)
        self.record_menu.setEnabled(not busy)
        if self.tray_stop is not None:
            self.tray_stop.setEnabled(self.recorder.active and not self.recorder.stopping)

