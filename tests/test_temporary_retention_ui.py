"""Qt integration tests for opt-in Temporary retention and normal shutdown."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from clipmint.app import ClipMintWindow


def add_old_temporary(window, text: bytes, pinned: bool = False) -> int:
    ident = window.store.add(
        "text", text, text.decode("utf-8"), "Temporary"
    )
    if pinned:
        window.store.pin(ident, True)
    timestamp = datetime.now(timezone.utc) - timedelta(days=3)
    window.store.conn.execute(
        "UPDATE clips SET created_at=? WHERE id=?",
        (timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
         ident),
    )
    window.store.conn.commit()
    return ident


class TemporaryRetentionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window_in(self, root):
        prefs = str(Path(root) / "temporary-prefs.ini")
        with patch("clipmint.app.QSettings",
                   side_effect=lambda *_args: QSettings(
                       prefs, QSettings.Format.IniFormat
                   )):
            return ClipMintWindow()

    def cleanup(self, window):
        if window is not None:
            window.poller.stop()
            window._vault_lock_timer.stop()
            window._temporary_expiry_timer.stop()
            window._closing = True
            if not window.store.closed:
                window.store.close()
            window.close()

    def test_defaults_are_off_and_upgrade_does_not_erase_any_clips(self):
        with TemporaryDirectory() as root:
            original = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = self.window_in(root)
                self.assertFalse(window.temporary_expiry_toggle.isChecked())
                self.assertFalse(window.temporary_exit_toggle.isChecked())
                self.assertFalse(window._temporary_expiry_timer.isActive())
                old = add_old_temporary(window, b"retain older item by default")
                window.expire_temporary_if_enabled()
                self.assertIsNotNone(window.store.get(old))
                window.quit_app()
                self.assertTrue(window.store.closed)
                window.poller.stop()
                window._temporary_expiry_timer.stop()
                window = self.window_in(root)
                self.assertIsNotNone(window.store.get(old))
                self.assertEqual(window.store.count("Temporary"), 1)
                self.assertFalse(window.temporary_expiry_toggle.isChecked())
            finally:
                self.cleanup(window)
                if original is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = original

    def test_expiry_confirmation_and_opt_out_are_respected(self):
        with TemporaryDirectory() as root:
            original = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = self.window_in(root)
                old = add_old_temporary(window, b"expired by opt-in")
                pinned = add_old_temporary(window, b"pinned survives expiry",
                                           pinned=True)
                window.paste_queue.add(old)
                window.quick_popup.refresh()
                self.assertTrue(any(
                    window.quick_popup.items.item(i).data(
                        Qt.ItemDataRole.UserRole
                    ) == old
                    for i in range(window.quick_popup.items.count())
                ))
                with patch.object(QMessageBox, "question",
                                  return_value=QMessageBox.StandardButton.No):
                    window.temporary_expiry_toggle.setChecked(True)
                self.assertFalse(window.temporary_expiry_toggle.isChecked())
                self.assertFalse(window._temporary_expiry_timer.isActive())
                self.assertIsNotNone(window.store.get(old))

                with patch.object(QMessageBox, "question",
                                  return_value=QMessageBox.StandardButton.Yes):
                    window.temporary_expiry_toggle.setChecked(True)
                self.assertTrue(window._temporary_expiry_timer.isActive())
                self.assertIsNone(window.store.get(old))
                self.assertIsNotNone(window.store.get(pinned))
                self.assertEqual(window.paste_queue.ids(), ())
                # Hidden quick-search results must not retain deleted IDs.
                self.assertEqual(window.quick_popup.items.count(), 0)
                window.store.add("text", b"fresh work copy", "fresh work copy", "Work")
                self.assertEqual(window.paste_queue.ids(), ())

                window.temporary_expiry_toggle.setChecked(False)
                self.assertFalse(window._temporary_expiry_timer.isActive())
                another = add_old_temporary(window, b"disabled retains this")
                window.expire_temporary_if_enabled()
                self.assertIsNotNone(window.store.get(another))
            finally:
                self.cleanup(window)
                if original is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = original

    def test_all_history_copy_paths_renew_temporary_clock(self):
        from PySide6.QtWidgets import QListWidgetItem
        with TemporaryDirectory() as root:
            previous = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = self.window_in(root)
                ident = add_old_temporary(window, b"reused scratchpad clip")
                from_history = QListWidgetItem("reused scratchpad clip")
                from_history.setData(Qt.ItemDataRole.UserRole, ident)

                for route in ("copy_clip", "_copy_entry_by_id", "quick_pick"):
                    with self.subTest(route=route):
                        old = datetime.now(timezone.utc) - timedelta(days=3)
                        window.store.conn.execute(
                            "UPDATE clips SET created_at=? WHERE id=?",
                            (old.isoformat(timespec="milliseconds").replace(
                                "+00:00", "Z"
                            ), ident),
                        )
                        window.store.conn.commit()
                        if route == "copy_clip":
                            window.copy_clip(from_history)
                        elif route == "_copy_entry_by_id":
                            self.assertTrue(window._copy_entry_by_id(ident))
                        else:
                            window.quick_pick(ident, False, None, "")
                        self.assertEqual(
                            window.store.expire_temporary_unpinned(), 0
                        )
                        self.assertIsNotNone(window.store.get(ident))

                # Work items are unaffected by Temporary's clock.
                work = window.store.add("text", b"Work reference",
                                        "Work reference", "Work")
                before = window.store.conn.execute(
                    "SELECT created_at FROM clips WHERE id=?", (work,)
                ).fetchone()[0]
                self.assertTrue(window._copy_entry_by_id(work))
                after = window.store.conn.execute(
                    "SELECT created_at FROM clips WHERE id=?", (work,)
                ).fetchone()[0]
                self.assertEqual(after, before)
            finally:
                self.cleanup(window)
                if previous is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous

    def test_modal_delete_cannot_target_a_new_clip_after_expiry(self):
        with TemporaryDirectory() as root:
            previous = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = self.window_in(root)
                expired = add_old_temporary(window, b"modal old item")
                index = window.bin_filter.findData("Temporary")
                self.assertGreater(index, 0)
                window.bin_filter.setCurrentIndex(index)
                window.refresh()
                self.assertEqual(window.history.count(), 1)
                window.history.setCurrentRow(0)
                self.assertEqual(window.selected_id(), expired)
                window.settings.setValue("temporary/expire_24h", True)
                window.update_temporary_expiry_schedule()
                replacement_ids = []

                def confirm_after_retention(*args, **kwargs):
                    window.expire_temporary_if_enabled()
                    new_id = window.store.add(
                        "text", b"totally different new Work content",
                        "totally different new Work content", "Work"
                    )
                    replacement_ids.append(new_id)
                    return QMessageBox.StandardButton.Yes

                with patch.object(QMessageBox, "question",
                                  side_effect=confirm_after_retention):
                    window.delete_selected()
                self.assertEqual(len(replacement_ids), 1)
                self.assertGreater(replacement_ids[0], expired)
                self.assertIsNotNone(window.store.get(replacement_ids[0]))
                self.assertIsNone(window.store.get(expired))
            finally:
                self.cleanup(window)
                if previous is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous

    def test_exit_setting_skips_tray_hide_but_runs_on_real_quit(self):
        with TemporaryDirectory() as root:
            original = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = self.window_in(root)
                unpinned = window.store.add(
                    "text", b"temporary scratchpad", "temporary scratchpad",
                    "Temporary"
                )
                pinned = window.store.add(
                    "text", b"pinned reference", "pinned reference", "Temporary"
                )
                work = window.store.add(
                    "text", b"work stays", "work stays", "Work"
                )
                window.store.pin(pinned, True)
                window.temporary_exit_toggle.setChecked(True)
                window.settings.sync()

                # Closing to a system tray is not an application shutdown.
                tray = MagicMock()
                window.tray = tray
                close_event = QCloseEvent()
                window.closeEvent(close_event)
                self.assertFalse(close_event.isAccepted())
                self.assertIsNotNone(window.store.get(unpinned))
                self.assertIsNotNone(window.store.get(pinned))

                window.quit_app()
                self.assertTrue(window.store.closed)
                window.poller.stop()
                window._temporary_expiry_timer.stop()
                window = self.window_in(root)
                self.assertIsNone(window.store.get(unpinned))
                self.assertIsNotNone(window.store.get(pinned))
                self.assertIsNotNone(window.store.get(work))
                self.assertTrue(window.temporary_exit_toggle.isChecked())
                self.assertFalse(window.temporary_expiry_toggle.isChecked())
            finally:
                self.cleanup(window)
                if original is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = original


if __name__ == "__main__":
    unittest.main()
