"""Thirty classifier exemplars, privacy precedence and default routing tests.

All contents are synthetic; no actual keys, identities or accounts are used.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nacl.secret import SecretBox
from nacl import utils

from clipmint.autosort import route_clip, validate_rule, NEVER_CAPTURE
from clipmint.clipboard_formats import sensitive_text, sensitive_payload
from clipmint.secure_history import EncryptedClipStore
from clipmint.smart_types import (
    SMART_TYPES, TYPE_BY_KEY, DEFAULT_BINS, default_smart_rules, classify_smart,
)
from clipmint.store import ClipStore


class SmartTypesTests(unittest.TestCase):
    def test_thirty_distinct_presets_and_valid_targets(self):
        self.assertEqual(len(SMART_TYPES), 30)
        self.assertEqual(len({x.key for x in SMART_TYPES}), 30)
        self.assertEqual(len(default_smart_rules()), 30)
        bins = ["Work", "Personal", "Temporary", *DEFAULT_BINS]
        self.assertTrue(all(
            validate_rule(rule, bins) == rule for rule in default_smart_rules()
        ))
        for item in SMART_TYPES:
            if item.private:
                self.assertEqual(item.bin, NEVER_CAPTURE)
            else:
                self.assertIn(item.bin, DEFAULT_BINS)

    def test_examples_for_every_proposed_category(self):
        examples = {
            "plain-text": ("text", "These are ordinary workshop notes to edit later.", None),
            "rich-text": ("text", "A formatted title with bold text.",
                          {"text/html": b"<h2>A formatted title</h2><b>bold</b>"}),
            "markdown": ("text", "# Heading\n- First bullet\n- Second bullet", None),
            "web-urls": ("text", "https://example.org/reference", None),
            "tracking-urls": ("text", "https://example.org/?utm_source=synthetic", None),
            "source-code": ("text", "def example(value):\n    return value + 2", None),
            "cli": ("text", "sudo apt update", None),
            "json": ("text", '{"sample": true, "count": 2}', None),
            "yaml-xml": ("text", "server: local\nport: 8080", None),
            "passwords": ("text", "CLIENT_SECRET=FAKE_client_123456", None),
            "otp": ("text", "834261", None),
            "api-keys": ("text", "ghp_" + "Ab2_" * 10, None),
            "email": ("text", "someone@example.org", None),
            "phone": ("text", "+27 82 123 4567", None),
            "postal-addresses": ("text", "125 Main Street\nSpringfield 0123", None),
            "payment-cards": ("text", "4111 1111 1111 1111", None),
            "banking": ("text", "IBAN: DE89370400440532013000", None),
            "crypto-wallets": ("text", "0x" + "a1" * 20, None),
            "images": ("image", "", {"image/png": b"fake"}),
            "svg": ("text", '<svg xmlns="http://www.w3.org/2000/svg"></svg>', None),
            "colors": ("text", "#FF5733", None),
            "tables": ("text", "name,quantity\nbolt,3\nnut,12", None),
            "local-paths": ("text", "/etc/hosts", None),
            "os-files": ("files", "file:///tmp/demo.txt", None),
            "package-tracking": ("text", "1Z999AA10123456784", None),
            "calendar-dates": ("text", "2026-11-04T13:19:00+02:00", None),
            "logs": ("text", "Traceback (most recent call last):\n"
                                 '  File "/tmp/demo.py", line 9', None),
            "hashes": ("text", "SHA-256 " + "a" * 64, None),
            "math": ("text", r"\int x^2 dx", None),
            "templates": ("text", "Dear {{customer}}, thanks for your order.", None),
        }
        self.assertEqual(set(examples), {item.key for item in SMART_TYPES})
        for expected, (kind, value, formats) in examples.items():
            with self.subTest(category=expected):
                detected = classify_smart(kind, value, formats)
                self.assertEqual(detected, expected)
                choice = route_clip(
                    default_smart_rules(), kind, value, "Work",
                    ["Work", *DEFAULT_BINS], formats=formats,
                )
                self.assertEqual(choice, None if TYPE_BY_KEY[expected].private
                                 else TYPE_BY_KEY[expected].bin)

    def test_override_custom_rules_and_retention_protection(self):
        bins = ["Work", *DEFAULT_BINS]
        rules = [
            {"mode": "Keyword", "pattern": "inspection", "target": "Work",
             "enabled": True},
            *default_smart_rules(),
        ]
        self.assertEqual(route_clip(rules, "text", "inspection notes",
                                    "Writing", bins), "Work")
        # Sensitive data must not bypass protection even with a top-level
        # permissive Text rule and disabled built-in private rules.
        permissive = [
            {"mode": "Text", "pattern": "", "target": "Work",
             "enabled": True},
            *[{**item, "enabled": False} for item in default_smart_rules()],
        ]
        for value in ("834261", "4111 1111 1111 1111",
                      "CLIENT_SECRET=synthetic_credential",
                      "GITHUB_CLIENT_SECRET=Example_NotReal1234",
                      "CLICKUP_TOKEN_KEY=synthetic_not_real_1234",
                      "MY_ACCESS_TOKEN=synthetic_not_real_1234"):
            with self.subTest(value=value[:6]):
                self.assertIsNone(route_clip(permissive, "text", value,
                                             "Work", bins))
                self.assertTrue(sensitive_text(value))
        with self.assertRaises(ValueError):
            validate_rule(
                {"mode": "Smart", "pattern": "passwords",
                 "target": "Work", "enabled": True}, bins
            )

    def test_plaintext_and_encrypted_stores_reject_direct_secret_inserts(self):
        with TemporaryDirectory() as root:
            path = Path(root)
            key = utils.random(SecretBox.KEY_SIZE)
            stores = (
                ClipStore(path / "ordinary.sqlite3"),
                EncryptedClipStore(path / "encrypted.sqlite3", key),
            )
            try:
                for store in stores:
                    with self.subTest(store=store.__class__.__name__):
                        self.assertIsNone(store.add(
                            "text", b"834261", "834261",
                            "Work", formats={"text/html": b"<b>834261</b>"},
                        ))
                        self.assertIsNone(store.add(
                            "text", b"Ordinary text", "Ordinary text",
                            "Work", formats={
                                "text/html": b"<b>CLIENT_SECRET=FAKE_secret123</b>"
                            },
                        ))
                        self.assertEqual(store.count("Work"), 0)
                        self.assertIsNotNone(store.add(
                            "text", b"Normal article text", "Normal article text"
                        ))
                        self.assertEqual(store.count("Work"), 1)
            finally:
                for store in stores:
                    store.close()

    def test_sensitive_payload_blocks_plain_and_html(self):
        self.assertTrue(sensitive_payload(
            "text", b"Ordinary paragraph",
            {"text/html": b"Authorization: Bearer example.fake.token012345"},
        ))
        self.assertFalse(sensitive_payload(
            "text", b"Normal notes", {"text/html": b"<b>Normal notes</b>"}
        ))


if __name__ == "__main__":
    unittest.main()
