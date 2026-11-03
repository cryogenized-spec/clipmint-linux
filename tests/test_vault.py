"""Vault at-rest secrecy, authenticated decryption and lifecycle tests.

All credentials here are fake test fixtures.
"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from clipmint.vault import Vault, VaultError


class VaultTests(unittest.TestCase):
    def test_create_lock_unlock_export_rotate_and_wipe(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "secrets.vault"
            vault = Vault(path)
            vault.create("fake-passphrase-123")
            self.assertTrue(vault.unlocked)
            entry_id = vault.add("fake API variable", "not-a-real-api-key-xyz", "Secret")
            vault.add("region", "South Africa", "Variable")
            self.assertNotIn(b"not-a-real-api-key-xyz", path.read_bytes())
            self.assertNotIn(b"fake API variable", path.read_bytes())
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            exported = Path(root) / "backup.json"
            vault.encrypted_backup(exported)
            self.assertEqual(exported.read_bytes(), path.read_bytes())
            self.assertEqual(os.stat(exported).st_mode & 0o777, 0o600)
            restored = Vault(Path(root) / "restored.vault")
            restored.restore_backup(exported)
            restored.unlock("fake-passphrase-123")
            self.assertEqual(restored.get_value(entry_id), "not-a-real-api-key-xyz")
            restored.lock()
            vault.lock()
            with self.assertRaises(VaultError):
                vault.get_value(entry_id)
            with self.assertRaises(VaultError):
                vault.unlock("incorrect-password")
            vault.unlock("fake-passphrase-123")
            self.assertEqual(vault.get_value(entry_id), "not-a-real-api-key-xyz")
            vault.change_passphrase("fake-passphrase-123", "different-fake-passphrase-abc")
            vault.lock()
            with self.assertRaises(VaultError):
                vault.unlock("fake-passphrase-123")
            vault.unlock("different-fake-passphrase-abc")
            vault.remove(entry_id)
            self.assertEqual(len(vault.list_entries()), 1)
            vault.wipe()
            self.assertFalse(path.exists())
            self.assertFalse(vault.unlocked)

    def test_rejects_tampering_and_short_password(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "vault"
            vault = Vault(path)
            with self.assertRaises(VaultError):
                vault.create("too-short")
            vault.create("fake-passphrase-123")
            vault.lock()
            data = json.loads(path.read_text())
            data["ciphertext"] = "AAAA"
            path.write_text(json.dumps(data))
            with self.assertRaises(VaultError):
                vault.unlock("fake-passphrase-123")


if __name__ == "__main__":
    unittest.main()
