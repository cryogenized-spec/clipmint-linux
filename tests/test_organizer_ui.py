"""Native Gothic archive controls for tags, favourites, snippets and queue."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication, QInputDialog
from PySide6.QtCore import Qt
from clipmint.app import ClipMintWindow
from clipmint.organizer_ui import TemplatesDialog, TransformDialog


class OrganizerUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = TemporaryDirectory()
        self.old = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self.root.name
        self.window = ClipMintWindow()
        self.window.resize(1480, 940)
        self.window.show()
        self.qt.processEvents()

    def tearDown(self):
        self.window.poller.stop()
        self.window._vault_lock_timer.stop()
        self.window.monitoring = False
        self.window.store.close()
        self.window.close()
        self.window.deleteLater()
        self.qt.processEvents()
        if self.old is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old
        self.root.cleanup()

    def select(self, ident):
        self.window.refresh()
        item = next(self.window.history.item(i) for i in range(self.window.history.count())
                    if self.window.history.item(i).data(Qt.ItemDataRole.UserRole) == ident)
        self.window.history.setCurrentItem(item)
        self.qt.processEvents()

    def test_tag_filter_favourites_and_full_body_search(self):
        entry = self.window.store.add(
            "text", b"Workshop invisible body contains NEWTON-CALIPER",
            "Workshop inspection preview"
        )
        self.window.store.set_tags(entry, ["repair", "urgent"])
        self.select(entry)
        self.assertIn("repair", self.window.preview_meta["Tags"].text())
        self.window.toggle_favorite_selected()
        self.assertTrue(self.window.store.is_favorite(entry))
        self.assertFalse(self.window.store.pinned(entry))
        self.window.favorites_filter.setChecked(True)
        self.window.search.setText("caliper")
        self.window.sort_combo.setCurrentIndex(
            self.window.sort_combo.findData("Best match")
        )
        self.qt.processEvents()
        self.assertEqual(self.window.history.count(), 1)
        self.assertIn("FTS5", self.window.search.toolTip())
        idx = self.window.tag_filter.findData("repair")
        self.assertNotEqual(idx, -1)
        self.window.tag_filter.setCurrentIndex(idx)
        self.assertEqual(self.window.history.count(), 1)
        self.window.tag_filter.setCurrentIndex(0)
        self.window.favorites_filter.setChecked(False)

    def test_paste_queue_stages_copies_without_typing(self):
        entry = self.window.store.add("text", b"queue example", "queue example")
        self.select(entry)
        with patch.object(self.window, "inform") as info:
            self.window.queue_add_selected()
            self.assertEqual(len(self.window.paste_queue), 1)
            self.assertTrue(self.window.queue_next_button.isEnabled())
            self.window.queue_copy_next()
            self.assertEqual(QApplication.clipboard().text(), "queue example")
            self.assertEqual(len(self.window.paste_queue), 0)
            self.assertFalse(self.window.queue_next_button.isEnabled())
            info.assert_called()

    def test_template_dialog_local_expansion(self):
        copied = []
        dialog = TemplatesDialog(self.window.store, copied.append)
        dialog.name.setText("Repair")
        dialog.editor.setPlainText("Hello {{customer}}, your repair is ready.")
        dialog.save_template()
        self.assertEqual(len(self.window.store.templates()), 1)
        with patch.object(QInputDialog, "getText", return_value=("Customer", True)):
            dialog.use_template()
        self.assertEqual(copied, ["Hello Customer, your repair is ready."])
        dialog.close()

    def test_transform_preview_copies_only_after_explicit_action(self):
        copied = []
        saved = []
        dialog = TransformDialog("hello", copied.append, saved.append)
        idx = dialog.operation.findText("Uppercase")
        dialog.operation.setCurrentIndex(idx)
        self.assertEqual(dialog.preview.toPlainText(), "HELLO")
        self.assertEqual(copied, [])
        dialog.copy_preview()
        self.assertEqual(copied, ["HELLO"])
        self.assertEqual(saved, [])
        dialog.close()


if __name__ == "__main__":
    unittest.main()
