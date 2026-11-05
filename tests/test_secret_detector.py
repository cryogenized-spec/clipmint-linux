"""Regression tests for centralised secret detection (synthetic data only)."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from clipmint.secret_detector import Confidence, detect_secret, looks_random, mask
from clipmint.clipboard_formats import sensitive_text
from clipmint.store import ClipStore, looks_sensitive


class SecretDetectorTests(unittest.TestCase):
    def test_source_hints_even_without_text(self):
        result = detect_secret("", mime_targets=["x-kde-passwordManagerHint"])
        self.assertTrue(result.is_secret)
        self.assertEqual(result.confidence, Confidence.HIGH)
        self.assertTrue(detect_secret("anything", source_app="org.keepassxc.KeePassXC").is_secret)

    def test_known_credentials(self):
        samples = (
            "sk-proj-" + "Ab2_" * 10,
            "github_pat_" + "Ab2_" * 15,
            "ghp_" + "Ab2_" * 10,
            "-----BEGIN OPENSSH PRIVATE KEY-----\nfake-key\n-----END OPENSSH PRIVATE KEY-----",
            "Authorization: Bearer " + "Abcd0123-" * 4,
            "postgresql://bob:fake-password@example.invalid/db",
            "eyJ" + "AbCd0123" * 2 + ".eyJ" + "AbCd0123" * 2 + ".Aa11Bb22Cc33",
        )
        for sample in samples:
            with self.subTest(sample=sample[:12]):
                self.assertTrue(detect_secret(sample).is_secret)
                self.assertTrue(sensitive_text(sample))
                self.assertTrue(looks_sensitive(sample))

    def test_env_assignments_and_unlabelled_keys(self):
        samples = (
            "CLICKUP_CLIENT_SECRET=FAKE_value_1234",
            "GITHUB_CLIENT_SECRET: fakevalue12345",
            '"OPENAI_API_KEY": "example-not-real"',
            "CLICKUP_TOKEN_KEY=FakeKey1234567",
            "password: fakepassword123",
            "Authorization: Bearer abc",
            "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/====",
            "a1b2c3d4" * 5,  # hex-like standalone token
        )
        for sample in samples:
            with self.subTest(sample=sample[:12]):
                self.assertTrue(detect_secret(sample).is_secret)

    def test_ordinary_text_exclusions(self):
        samples = (
            "This task needs an API key later; none has been issued.",
            "https://example.com/support/article",
            "someone@example.com",
            "12:34 2026-11-04",
            "00112233-4455-6677-8899-aabbccddeeff",
            "Invoice 2026-000001",
            "Don't archive this as a password.",
            "No tokens were copied today.",
            "abcdefgh",
            "HighlyUniqueTemporaryHistoryFtsCanaryZyxw987",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertFalse(detect_secret(sample).is_secret)

    def test_card_validation_and_masking(self):
        self.assertTrue(detect_secret("4111 1111 1111 1111").is_secret)
        self.assertFalse(detect_secret("4111 1111 1111 1112").is_secret)
        self.assertEqual(mask("different-secret", reveal=6), "\N{BULLET}" * 12)
        self.assertEqual(mask("a"), mask("a much longer value"))

    def test_bank_and_identity_labels_are_precise(self):
        sa = detect_secret("0001010000089")  # Synthetic, checksummed identifier.
        self.assertTrue(sa.is_secret)
        self.assertIn("South African identity number", sa.reasons)
        self.assertNotIn("payment card checksum", sa.reasons)
        iban = detect_secret("GB82 WEST 1234 5698 7654 32")
        self.assertTrue(iban.is_secret)
        self.assertIn("IBAN bank account checksum", iban.reasons)
        self.assertFalse(detect_secret("GB82 WEST 1234 5698 7654 33").is_secret)
        # Bare SHA1 and 40-hex credentials cannot be distinguished safely.
        # Maintain conservative redaction rather than silently allow keys.
        self.assertTrue(detect_secret("a1b2c3d4" * 5).is_secret)

    def test_history_rejects_credentials_even_on_direct_insert(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                secret = b"GITHUB_CLIENT_SECRET=fakeValue123"
                self.assertIsNone(store.add("text", secret, secret.decode()))
                self.assertEqual(store.count("Work"), 0)
                # A benign plaintext preview cannot conceal a secret HTML body.
                self.assertIsNone(store.add(
                    "text", b"Normal title", "Normal title",
                    formats={"text/html": b"<b>API_KEY=FAKE_abcdef12345</b>"}
                ))
                self.assertEqual(store.count("Work"), 0)
                self.assertIsNotNone(store.add("text", b"Repair note", "Repair note"))
                self.assertEqual(store.count("Work"), 1)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
