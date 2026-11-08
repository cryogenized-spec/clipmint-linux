"""The installed screenshot shortcut must bypass frozen Qt when ClipMint is hidden.

These tests use only user-owned temporary UNIX sockets and fake executables.
No Cinnamon settings, installed binaries, or real screenshot files are touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "packaging" / "clipmint-launcher.py"


class FastLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.entry = self.folder / "ClipMint"
        shutil.copyfile(LAUNCHER, self.entry)
        self.entry.chmod(0o755)
        self.stub = self.folder / "ClipMintApp"
        self.stub.write_text(
            "#!/usr/bin/python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['CLIPMINT_TEST_RESULT']).write_text(json.dumps(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        self.stub.chmod(0o755)
        self.output = self.folder / "result.json"
        self.env = {
            **os.environ,
            "TMPDIR": str(self.folder),
            "CLIPMINT_TEST_RESULT": str(self.output),
        }
        self.server_path = self.folder / f"clipmint-single-instance-{os.getuid()}"

    def invoke(self, *args):
        return subprocess.run(
            [str(self.entry), *args],
            env=self.env, capture_output=True, text=True, timeout=5,
            check=False,
        )

    def test_existing_hidden_watcher_gets_hotkey_without_gui_start(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.server_path))
            self.server_path.chmod(0o600)
            server.listen(1)
            server.settimeout(3)
            result = self.invoke("--screenshot-area")
            self.assertEqual(result.returncode, 0, result.stderr)
            with server.accept()[0] as conn:
                self.assertEqual(conn.recv(64), b"screenshot-area\n")
            self.assertFalse(self.output.exists(), "Frozen GUI was launched")

    def test_hidden_autostart_only_pings_existing_watcher(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.server_path))
            self.server_path.chmod(0o600)
            server.listen(1)
            server.settimeout(3)
            self.assertEqual(self.invoke("--hidden").returncode, 0)
            with server.accept()[0] as conn:
                self.assertEqual(conn.recv(64), b"ping\n")
            self.assertFalse(self.output.exists())

    def test_stopped_watcher_uses_full_app_without_losing_arguments(self):
        result = self.invoke("--screenshot-area")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text()), ["--screenshot-area"])

    def test_regular_file_cannot_impersonate_instance_socket(self):
        self.server_path.write_text("not a socket", encoding="utf-8")
        result = self.invoke("--screenshot-area")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text()), ["--screenshot-area"])

    def test_public_socket_is_never_contacted(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.server_path))
            self.server_path.chmod(0o666)
            server.listen(1)
            result = self.invoke("--screenshot-area")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(self.output.read_text()), ["--screenshot-area"])

    def test_quit_while_stopped_does_not_start_the_full_app(self):
        result = self.invoke("--quit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.output.exists())

    def test_package_contract_keeps_unchanged_shortcut_entry_point(self):
        launcher = LAUNCHER.read_text()
        package = (ROOT / "packaging" / "build-deb.sh").read_text()
        verifier = (ROOT / "packaging" / "verify-field-package.sh").read_text()
        app = (ROOT / "clipmint" / "app.py").read_text()
        self.assertTrue(launcher.startswith("#!/usr/bin/python3"))
        self.assertIn('mv "$root/opt/clipmint/ClipMint" "$root/opt/clipmint/ClipMintApp"', package)
        self.assertIn('install -m 755 packaging/clipmint-launcher.py', package)
        self.assertIn("python3, xz-utils, xdotool", package)
        self.assertIn('test -x "$tmp/unpacked/opt/clipmint/ClipMintApp"', verifier)
        self.assertIn('with_name("ClipMint")', app)
        self.assertIn("250 if had_visible_window else 0", app)


if __name__ == "__main__":
    unittest.main()
