"""Cinnamon global shortcuts and clipboard quick-popup actions.

Retain the existing explicit screenshot takeover prompts, Cinnamon conflict
checks, read-only audit, and user-controlled auto-paste behavior. The main
window still owns the clipboard/store and quick-popup widgets; this module
only supplies their existing callbacks.
"""
from __future__ import annotations

from pathlib import Path
import shlex
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox

from .cinnamon_hotkey import (
    ShortcutSetupError, install_shortcut, restore_screenshot_takeover,
    shortcut_conflicts,
)
from .history_clipboard_copy import copy_saved_clip, CopyOutcome
from .quick_popup import paste_to_window


class HotkeyPopupControllerMixin:
    """Window callbacks for global keys and fast clipboard access."""

    def register_cinnamon_hotkey(self):
        sequence = self.global_popup_hotkey.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not sequence:
            self.error("Cinnamon shortcut", "Choose a keyboard shortcut first")
            return
        executable = (shlex.quote(sys.executable)
                      if getattr(sys, "frozen", False) else
                      shlex.quote(sys.executable) + " " +
                      shlex.quote(str(Path(__file__).resolve().parent.parent / "launcher.py")))
        command = executable + " --toggle"
        try:
            accel = install_shortcut(command, sequence)
        except ShortcutSetupError as exc:
            self.error("Cinnamon shortcut", str(exc))
            return
        self.settings.setValue("popup/global_shortcut", sequence)
        self.inform("Cinnamon shortcut", f"Registered {sequence} ({accel})")

    def _clipmint_launcher_command(self, action: str) -> str:
        """Match the installed app launcher; never shell-expand user content."""
        if getattr(sys, "frozen", False):
            # The packaged stdlib launcher forwards commands straight to the
            # running watcher, avoiding a second PyInstaller/Qt startup.
            executable = shlex.quote(str(Path(sys.executable).with_name("ClipMint")))
        else:
            executable = (shlex.quote(sys.executable) + " " +
                          shlex.quote(str(Path(__file__).resolve().parent.parent / "launcher.py")))
        return executable + " " + action

    def register_cinnamon_screenshot_hotkey(self):
        sequence = self.global_screenshot_hotkey.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not sequence:
            self.error("Cinnamon screenshot shortcut", "Choose a keyboard shortcut first")
            return
        command = self._clipmint_launcher_command("--screenshot-area")
        try:
            accel = install_shortcut(command, sequence, name="ClipMint screenshot area")
        except ShortcutSetupError as exc:
            if "Explicit permission" not in str(exc):
                self.error("Cinnamon screenshot shortcut", str(exc))
                return
            reply = QMessageBox.question(
                self, "Give ClipMint screenshot priority?",
                "Cinnamon already uses this combination for its own screenshot "
                "tool. Give this combination to ClipMint instead?\n\n"
                "Only the conflicting built-in screenshot binding will be "
                "disabled; its other key combinations will be preserved. "
                "The original is saved for restoration. This changes your "
                "desktop shortcut configuration, not ClipMint's window-only keys.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                accel = install_shortcut(
                    command, sequence, name="ClipMint screenshot area",
                    take_over_screenshot=True,
                )
            except ShortcutSetupError as retry:
                self.error("Cinnamon screenshot shortcut", str(retry))
                return
        self.settings.setValue("capture/global_shortcut", sequence)
        self.inform("Cinnamon shortcut", f"ClipMint screenshot registered: {sequence}")

    def restore_cinnamon_screenshot_hotkey(self):
        sequence = str(self.settings.value("capture/global_shortcut", "Ctrl+Shift+S"))
        command = self._clipmint_launcher_command("--screenshot-area")
        reply = QMessageBox.question(
            self, "Restore Cinnamon screenshot shortcut?",
            "Remove ClipMint's registered screenshot key and restore the "
            "previous built-in screenshot assignment from the local backup? "
            "Existing user edits will not be overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            restored = restore_screenshot_takeover(command, sequence)
        except ShortcutSetupError as exc:
            self.error("Cinnamon screenshot restoration", str(exc))
            return
        self.inform("Cinnamon shortcut",
                    "Previous screenshot assignment restored"
                    if restored else "No ClipMint takeover backup found")

    def register_cinnamon_recording_hotkey(self):
        sequence = self.global_record_hotkey.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not sequence:
            self.error("Cinnamon recording shortcut", "Choose a keyboard shortcut first")
            return
        command = self._clipmint_launcher_command("--record-area")
        try:
            install_shortcut(command, sequence, name="ClipMint record area")
        except ShortcutSetupError as exc:
            self.error("Cinnamon recording shortcut", str(exc))
            return
        self.settings.setValue("capture/global_record_shortcut", sequence)
        self.inform("Cinnamon shortcut", f"ClipMint recorder registered: {sequence}")

    def audit_global_hotkeys(self):
        """Read-only report of who currently owns our configured global keys."""
        configured = (
            ("Screenshot", str(self.settings.value(
                "capture/global_shortcut", "Ctrl+Shift+S"
            )), self._clipmint_launcher_command("--screenshot-area")),
            ("Recording", str(self.settings.value(
                "capture/global_record_shortcut", "Ctrl+Shift+R"
            )), self._clipmint_launcher_command("--record-area")),
            ("Clipboard popup", str(self.settings.value(
                "popup/global_shortcut", "Ctrl+Alt+V"
            )), self._clipmint_launcher_command("--toggle")),
        )
        report = []
        for title, sequence, expected_command in configured:
            try:
                found = shortcut_conflicts(sequence)
            except ShortcutSetupError as exc:
                report.append(f"{title} · {sequence}: cannot inspect ({exc})")
                continue
            ours = [x for x in found if x["source"] == "custom"
                    and x.get("command") == expected_command]
            others = [x for x in found if x not in ours]
            if ours and not others:
                result = "Assigned to ClipMint in Cinnamon"
            elif others:
                result = "Conflict · another Cinnamon shortcut is assigned"
            else:
                result = "Not registered as a Cinnamon global shortcut"
            report.append(f"{title} · {sequence}: {result}")
        QMessageBox.information(
            self, "ClipMint · Cinnamon hotkeys",
            "\n".join(report) +
            "\n\nThis verifies Cinnamon assignments, not whether another "
            "application, extension or external shortcut daemon intercepts "
            "the same key. Confirm by pressing each shortcut outside ClipMint.",
        )

    def toggle_quick_popup(self):
        self.quick_popup.toggle()

    def quick_pick(self, clip_id: int, plain: bool, wid: str | None, klass: str):
        outcome = copy_saved_clip(
            self.store, lambda: self._own_clipboard_guard,
            QApplication.clipboard, clip_id, plain=plain,
        )
        if outcome == CopyOutcome.TEXT_ONLY:
            self.inform("Quick paste", "Plain paste works with text clips only")
            return
        if outcome != CopyOutcome.COPIED:
            return
        if wid and self.settings.value("popup/auto_paste", True, type=bool):
            QTimer.singleShot(150, lambda: self._paste_to_target(wid, klass))

    def _paste_to_target(self, wid: str, klass: str):
        mode = str(self.settings.value("popup/terminal_mode", "auto"))
        if not paste_to_window(wid, klass, mode):
            self.statusBar().showMessage(
                "Copied; automatic paste unavailable. Paste manually.", 7000
            )

