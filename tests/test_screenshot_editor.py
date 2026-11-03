"""User-requested screenshot notification and editor contract."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from clipmint.screenshot_editor import open_image_editor, resolve_editor
from clipmint.app import ClipMintWindow


class EditorResolutionTests(unittest.TestCase):
    def test_prefers_installed_editor_not_arbitrary_viewer(self):
        which = lambda x: "/usr/bin/" + x if x in {"pinta", "xdg-open"} else None
        self.assertEqual(resolve_editor("auto", which), (["pinta"], "Pinta", True))
        self.assertEqual(
            resolve_editor("system", which),
            (["xdg-open"], "system image application", False),
        )
        with self.assertRaises(FileNotFoundError):
            resolve_editor("krita", which)

    def test_launch_is_argv_not_shell_and_requires_existing_png(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "my picture;$(touch x).png"
            file.write_bytes(b"fixture")
            runner = Mock()
            which = lambda x: "/usr/bin/" + x if x == "gimp" else None
            self.assertEqual(
                open_image_editor(file, "gimp", which=which, popen=runner),
                ("GIMP", True)
            )
            args = runner.call_args.args[0]
            self.assertEqual(args, ["gimp", str(file)])
            self.assertTrue(runner.call_args.kwargs["start_new_session"])
            with self.assertRaises(FileNotFoundError):
                open_image_editor(file.with_suffix(".jpg"), "gimp", which=which,
                                  popen=runner)


class ScreenshotNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_capture_creates_clickable_editor_notice(self):
        with TemporaryDirectory() as root:
            previous = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.show()
                self.app.processEvents()
                image = QPixmap(80, 60)
                image.fill(QColor("#9B4558"))
                with patch("clipmint.app.screenshots_dir", return_value=Path(root)):
                    window.save_screenshot(None, image)
                self.app.processEvents()
                self.assertEqual(window._last_screenshot_path.suffix, ".png")
                self.assertTrue(window._last_screenshot_path.is_file())
                self.assertTrue(window.screenshot_notice.isVisible())
                self.assertEqual(window.screenshot_notice.edit_button.text(),
                                 "Edit screenshot")
                with patch("clipmint.app.open_image_editor",
                           return_value=("Pinta", True)) as opener:
                    window.screenshot_notice.edit_button.click()
                    self.assertEqual(opener.call_count, 1)
                    self.assertEqual(opener.call_args.args[0],
                                     window._last_screenshot_path)
                self.assertTrue(window.screenshot_notice.isHidden())
                window.notify_screenshot_captured(window._last_screenshot_path)
                current = window._screenshot_notice_token
                window.dismiss_screenshot_notice(current - 1)
                self.assertTrue(window.screenshot_notice.isVisible())
                window.dismiss_screenshot_notice(current)
                self.assertTrue(window.screenshot_notice.isHidden())
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.hide()
                if previous is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous


if __name__ == "__main__":
    unittest.main()
