"""Safety contracts for extracted tray and application lifecycle callbacks.

All platform tray, clipboard and window operations are mocked. No real
desktop configuration is changed.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.app_lifecycle_controller import AppLifecycleMixin


class AppLifecycleRefactorTests(unittest.TestCase):
    def test_original_callbacks_remain_available_on_window(self):
        self.assertTrue(issubclass(ClipMintWindow, AppLifecycleMixin))
        for name in (
            "set_login_startup_enabled", "configure_tray",
            "tray_activated", "show_window", "tray_notification_clicked",
            "inform", "error", "closeEvent", "quit_app",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(ClipMintWindow, name),
                              getattr(AppLifecycleMixin, name))

    def test_close_to_background_hides_but_never_stops_history(self):
        event=SimpleNamespace(ignore=Mock(), accept=Mock())
        state=SimpleNamespace(_closing=False, lock_vault=Mock(), hide=Mock())
        AppLifecycleMixin.closeEvent(state, event)
        state.lock_vault.assert_called_once_with()
        state.hide.assert_called_once_with()
        event.ignore.assert_called_once_with()
        event.accept.assert_not_called()

    def test_close_after_explicit_quit_accepts_event(self):
        event=SimpleNamespace(ignore=Mock(), accept=Mock())
        state=SimpleNamespace(_closing=True, lock_vault=Mock(), hide=Mock())
        AppLifecycleMixin.closeEvent(state, event)
        event.accept.assert_called_once_with()
        event.ignore.assert_not_called()
        state.hide.assert_not_called()

    def test_active_recording_refuses_shutdown_without_cleanup(self):
        state=SimpleNamespace(
            recorder=SimpleNamespace(process=object()),
            error=Mock(), lock_vault=Mock(),
            clear_temporary_on_normal_exit=Mock(), store=SimpleNamespace(close=Mock()),
        )
        with patch("clipmint.app_lifecycle_controller.QApplication") as app:
            AppLifecycleMixin.quit_app(state)
        state.error.assert_called_once()
        state.lock_vault.assert_not_called()
        state.clear_temporary_on_normal_exit.assert_not_called()
        state.store.close.assert_not_called()
        app.quit.assert_not_called()

    def test_explicit_quit_stops_watchers_and_closes_store(self):
        events=[]
        record=lambda name: Mock(side_effect=lambda *args: events.append(name))
        state=SimpleNamespace(
            recorder=SimpleNamespace(process=None),
            recorder_window=None, _closing=False,
            _auto_update_timer=SimpleNamespace(stop=record("updater")),
            _hidden_clipboard_timer=SimpleNamespace(stop=record("hidden-poll")),
            lock_vault=record("vault"),
            clear_temporary_on_normal_exit=record("temporary"),
            store=SimpleNamespace(close=record("store")),
            tray=SimpleNamespace(hide=record("tray")),
        )
        with patch("clipmint.app_lifecycle_controller.QApplication") as app:
            AppLifecycleMixin.quit_app(state)
        self.assertTrue(state._closing)
        self.assertEqual(events, [
            "updater", "hidden-poll", "vault", "temporary", "store", "tray",
        ])
        app.quit.assert_called_once_with()

    def test_reopening_hidden_window_recovers_current_clipboard_first(self):
        events=[]
        state=SimpleNamespace(
            isVisible=lambda: False,
            poll_hidden_clipboard=lambda: events.append("poll"),
            showNormal=lambda: events.append("show"),
            raise_=lambda: events.append("raise"),
            activateWindow=lambda: events.append("activate"),
        )
        AppLifecycleMixin.show_window(state)
        self.assertEqual(events, ["poll", "show", "raise", "activate"])

    def test_unavailable_system_tray_is_not_required_for_background_mode(self):
        state=SimpleNamespace()
        with patch("clipmint.app_lifecycle_controller.QSystemTrayIcon") as tray:
            tray.isSystemTrayAvailable.return_value=False
            AppLifecycleMixin.configure_tray(state)
            tray.assert_not_called()
        self.assertIsNone(state.tray)
        self.assertIsNone(state.tray_stop)


if __name__ == "__main__":
    unittest.main()
