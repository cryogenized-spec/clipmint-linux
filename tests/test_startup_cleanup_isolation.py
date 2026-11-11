"""Startup failure isolation and deterministic IPC/socket cleanup."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from clipmint import app as app_module
from clipmint.app_lifecycle_controller import AppLifecycleMixin
from clipmint import single_instance


class StartupAndCleanupTests(unittest.TestCase):
    def test_instance_lock_acquired_before_window_initialization(self):
        order = []
        win = Mock()

        def make_instance(*args, **kwargs):
            order.append("lock")
            return Mock()

        def make_window():
            order.append("window")
            return win

        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}), \
             patch("clipmint.app.sys.argv", ["clipmint"]), \
             patch("clipmint.app.QApplication") as qt, \
             patch("clipmint.app.send_command", return_value=False), \
             patch("clipmint.app.InstanceServer", side_effect=make_instance) as server, \
             patch("clipmint.app.ClipMintWindow", side_effect=make_window):
            qt.return_value.exec.return_value = 0
            with self.assertRaises(SystemExit):
                app_module.main()
        self.assertEqual(order, ["lock", "window"])
        server.assert_called_once()
        win.show.assert_called_once()

    def test_window_startup_error_releases_lock(self):
        instance = Mock()
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}), \
             patch("clipmint.app.sys.argv", ["clipmint"]), \
             patch("clipmint.app.QApplication"), \
             patch("clipmint.app.send_command", return_value=False), \
             patch("clipmint.app.InstanceServer", return_value=instance), \
             patch("clipmint.app.ClipMintWindow", side_effect=RuntimeError("init failed")):
            with self.assertRaisesRegex(RuntimeError, "init failed"):
                app_module.main()
        instance.close.assert_called_once_with()

    def test_failed_cleanup_does_not_skip_store_and_instance_release(self):
        steps = []
        def task(name, broken=False):
            def run():
                steps.append(name)
                if broken:
                    raise OSError("simulated cleanup fault")
            return Mock(side_effect=run)

        state = SimpleNamespace(
            _quit_complete=False,
            recorder=SimpleNamespace(process=None), recorder_window=None,
            _runtime_timers=SimpleNamespace(stop_all=task("timers", broken=True)),
            lock_vault=task("vault", broken=True),
            clear_temporary_on_normal_exit=task("retention"),
            store=SimpleNamespace(close=task("db")),
            tray=SimpleNamespace(hide=task("tray")),
            _instance_server=SimpleNamespace(close=task("lock")),
        )
        with patch("clipmint.app_lifecycle_controller.QApplication") as qt, \
             patch("clipmint.app_lifecycle_controller.QMessageBox") as msg:
            AppLifecycleMixin._finish_quit(state)
        self.assertEqual(
            steps, ["timers", "vault", "retention", "db", "tray", "lock"]
        )
        self.assertTrue(state._quit_complete)
        msg.warning.assert_called_once()
        self.assertNotIn("simulated cleanup fault", msg.warning.call_args.args[2])
        qt.quit.assert_called_once_with()

    def test_socket_close_error_still_releases_advisory_lock(self):
        server = Mock()
        server.close.side_effect = OSError("socket close failed")
        state = SimpleNamespace(server=server, _lock_fd=1234)
        with patch("clipmint.single_instance.os.close") as close:
            with self.assertRaisesRegex(OSError, "socket close failed"):
                single_instance.InstanceServer.close(state)
        close.assert_called_once_with(1234)
        self.assertIsNone(state._lock_fd)

    def test_ipc_close_is_idempotent(self):
        state = SimpleNamespace(server=Mock(), _lock_fd=1234)
        with patch("clipmint.single_instance.os.close") as close:
            single_instance.InstanceServer.close(state)
            single_instance.InstanceServer.close(state)
        close.assert_called_once_with(1234)


if __name__ == "__main__":
    unittest.main()
