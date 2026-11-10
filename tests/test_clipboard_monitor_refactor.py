"""Behavioral contracts for extracted X11 clipboard monitor and privacy gates."""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.clipboard_monitor import ClipboardMonitorMixin


class ClipboardMonitorRefactorTests(unittest.TestCase):
    def test_main_window_inherits_exact_clipboard_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, ClipboardMonitorMixin))
        for name in (
            "_clipboard_generation_changed", "poll_hidden_clipboard",
            "clipboard_changed", "expire_sensitive_clipboard",
            "toggle_monitoring",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(ClipMintWindow, name),
                              getattr(ClipboardMonitorMixin, name))

    def test_paused_monitor_observes_but_does_not_capture(self):
        data = object()
        state = SimpleNamespace(
            _hidden_text_probe=SimpleNamespace(observe=Mock()),
            _own_clipboard_guard=SimpleNamespace(consume=Mock(return_value=False)),
            monitoring=False, _closing=False, store=SimpleNamespace(closed=False),
        )
        with patch("clipmint.clipboard_monitor.QApplication.clipboard") as clipboard:
            clipboard.return_value.mimeData.return_value = data
            ClipboardMonitorMixin.clipboard_changed(state)
        state._hidden_text_probe.observe.assert_called_once_with(data)
        state._own_clipboard_guard.consume.assert_called_once_with(data)

    def test_own_clipboard_write_is_skipped_even_while_monitoring(self):
        data = object()
        state = SimpleNamespace(
            _hidden_text_probe=SimpleNamespace(observe=Mock()),
            _own_clipboard_guard=SimpleNamespace(consume=Mock(return_value=True)),
            monitoring=True, _closing=False, store=SimpleNamespace(closed=False),
        )
        with patch("clipmint.clipboard_monitor.QApplication.clipboard") as clipboard, \
             patch("clipmint.clipboard_monitor.from_mime") as decode:
            clipboard.return_value.mimeData.return_value = data
            ClipboardMonitorMixin.clipboard_changed(state)
        decode.assert_not_called()

    def test_hidden_poll_does_not_ingest_while_paused(self):
        data = object()
        state = SimpleNamespace(
            _closing=False, store=SimpleNamespace(closed=False),
            isVisible=lambda: False,
            _hidden_text_probe=SimpleNamespace(observe=Mock(return_value=True)),
            monitoring=False, history_security_error="",
            clipboard_changed=Mock(),
        )
        with patch("clipmint.clipboard_monitor.QApplication.clipboard") as clipboard:
            clipboard.return_value.mimeData.return_value = data
            ClipboardMonitorMixin.poll_hidden_clipboard(state)
        state._hidden_text_probe.observe.assert_called_once_with(data)
        state.clipboard_changed.assert_not_called()

    def test_expiry_token_does_not_clear_new_clipboard_value(self):
        state = SimpleNamespace(_sensitive_clipboard_token=4)
        with patch("clipmint.clipboard_monitor.QApplication.clipboard") as clipboard:
            ClipboardMonitorMixin.expire_sensitive_clipboard(
                state, 3, "secret never persisted"
            )
            clipboard.assert_not_called()
            clipboard.return_value.text.return_value = "newer clipboard"
            ClipboardMonitorMixin.expire_sensitive_clipboard(
                state, 4, "secret never persisted"
            )
            clipboard.return_value.clear.assert_not_called()

    def test_resuming_monitoring_baselines_existing_clipboard(self):
        data = object()
        probe=SimpleNamespace(observe=Mock())
        state=SimpleNamespace(
            monitoring=False, history_security_error="",
            _hidden_text_probe=probe,
            pause_button=SimpleNamespace(setText=Mock()),
            refresh=Mock(), inform=Mock(),
        )
        with patch("clipmint.clipboard_monitor.QApplication.clipboard") as clipboard:
            clipboard.return_value.mimeData.return_value = data
            ClipboardMonitorMixin.toggle_monitoring(state)
        self.assertTrue(state.monitoring)
        probe.observe.assert_called_once_with(data)
        state.pause_button.setText.assert_called_once_with("Pause monitoring")


if __name__ == "__main__":
    unittest.main()
