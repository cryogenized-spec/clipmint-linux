"""Runtime ownership and safe OCR completion during explicit shutdown."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from clipmint.runtime_timers import RuntimeTimers
from clipmint.app_lifecycle_controller import AppLifecycleMixin
from clipmint.ocr_controller import OcrControllerMixin


class RuntimeShutdownTests(unittest.TestCase):
    def test_timer_registry_stops_all_once(self):
        timers = {name: Mock() for name in (
            "auto_update", "hidden_clipboard", "temporary_expiry",
            "history_search", "recorder_poll", "vault_lock",
        )}
        runtime = RuntimeTimers(**timers)
        runtime.stop_all()
        runtime.stop_all()
        for timer in timers.values():
            timer.stop.assert_called_once_with()

    def test_timer_failure_still_stops_remaining(self):
        a, b = Mock(), Mock()
        a.stop.side_effect = RuntimeError("timer unavailable")
        with self.assertRaisesRegex(RuntimeError, "timer 'first'"):
            RuntimeTimers(first=a, second=b).stop_all()
        b.stop.assert_called_once()

    def test_active_ocr_defers_quit_without_destroying_worker(self):
        worker = SimpleNamespace(isRunning=lambda: True)
        state = SimpleNamespace(
            _closing=False, _quit_pending=False, _quit_complete=False,
            _ocr_workers=[worker],
            recorder=SimpleNamespace(process=None),
            statusBar=lambda: SimpleNamespace(showMessage=Mock()),
            store=SimpleNamespace(close=Mock()),
        )
        with patch("clipmint.app_lifecycle_controller.QApplication") as app:
            AppLifecycleMixin.quit_app(state)
        self.assertTrue(state._quit_pending)
        self.assertTrue(state._closing)
        state.store.close.assert_not_called()
        app.quit.assert_not_called()

    def test_ocr_completion_finishes_pending_quit_exactly_once(self):
        worker = Mock()
        worker.isRunning.return_value = False
        state = SimpleNamespace(
            _ocr_workers={worker}, _quit_pending=True,
            _finish_quit=Mock(),
        )
        OcrControllerMixin._ocr_worker_finished(state, worker)
        self.assertEqual(state._ocr_workers, set())
        worker.deleteLater.assert_called_once()
        state._finish_quit.assert_called_once()

    def test_late_ocr_text_never_writes_clipboard_or_history(self):
        state = SimpleNamespace(_closing=True)
        with patch("clipmint.ocr_controller.QApplication") as app:
            OcrControllerMixin.ocr_recognized(state, "private OCR text")
        app.clipboard.assert_not_called()

    def test_repeating_quit_after_completion_is_noop(self):
        state = SimpleNamespace(_quit_complete=True, recorder=Mock())
        with patch("clipmint.app_lifecycle_controller.QApplication") as app:
            AppLifecycleMixin.quit_app(state)
        app.quit.assert_not_called()

    def test_normal_shutdown_releases_instance_lock(self):
        events = []
        def step(name):
            return Mock(side_effect=lambda: events.append(name))
        state = SimpleNamespace(
            _quit_complete=False, recorder=SimpleNamespace(process=None),
            recorder_window=None,
            _runtime_timers=SimpleNamespace(stop_all=step("timers")),
            lock_vault=step("vault"),
            clear_temporary_on_normal_exit=step("retention"),
            store=SimpleNamespace(close=step("store")),
            tray=SimpleNamespace(hide=step("tray")),
            _instance_server=SimpleNamespace(close=step("instance")),
        )
        with patch("clipmint.app_lifecycle_controller.QApplication") as app:
            AppLifecycleMixin._finish_quit(state)
        self.assertEqual(events, [
            "timers", "vault", "retention", "store", "tray", "instance",
        ])
        self.assertTrue(state._quit_complete)
        app.quit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
