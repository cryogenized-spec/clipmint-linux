"""Autosort first-match precedence, opt-out and hostile data regression checks."""
import unittest

from clipmint.autosort import validate_rule, route_clip, NEVER_CAPTURE

BINS = ["Work", "Personal", "Temporary"]


def rule(mode, target, pattern="", enabled=True):
    return {"mode": mode, "target": target, "pattern": pattern, "enabled": enabled}


class AutosortTests(unittest.TestCase):
    def test_disabled_and_first_match_precedence(self):
        rules = [
            rule("Keyword", "Personal", "invoice", False),
            rule("URL", "Temporary"),
            rule("Keyword", "Personal", "invoice"),
            rule("Text", "Work"),
        ]
        self.assertEqual(route_clip(rules, "text", "https://example.org/invoice",
                                    "Work", BINS), "Temporary")
        self.assertEqual(route_clip(rules, "text", "Invoice number 1",
                                    "Work", BINS), "Personal")
        self.assertEqual(route_clip([], "text", "hello", "Personal", BINS),
                         "Personal")

    def test_image_phone_and_regex(self):
        rules = [rule("Image", "Temporary"), rule("Phone", "Personal"),
                 rule("Regex", "Work", r"INV\d{5}")]
        self.assertEqual(route_clip(rules, "image", "", "Work", BINS), "Temporary")
        self.assertEqual(route_clip(rules, "text", "+27 82 123 4567",
                                    "Work", BINS), "Personal")
        self.assertEqual(route_clip(rules, "text", "INV50012",
                                    "Personal", BINS), "Work")

    def test_exclude_and_corrupt_rules(self):
        rules = [rule("Keyword", NEVER_CAPTURE, "do not retain"),
                 {"mode": "Eval", "pattern": "x", "target": "Work"},
                 rule("Text", "Personal")]
        self.assertIsNone(route_clip(rules, "text", "do not retain", "Work", BINS))
        self.assertEqual(route_clip(rules, "text", "ordinary", "Work", BINS),
                         "Personal")
        self.assertRaises(ValueError, validate_rule,
                          rule("Regex", "Work", "(unclosed"), BINS)
        self.assertRaises(ValueError, validate_rule,
                          rule("Text", "Unknown"), BINS)

    def test_regex_never_runs_python_code(self):
        payload = "__import__('os').system('touch /tmp/injected')"
        rules = [rule("Regex", "Personal", r"__import__")]
        self.assertEqual(route_clip(rules, "text", payload, "Work", BINS),
                         "Personal")
        # Invalid rule is skipped, not evaluated; no Python execution API exists.
        self.assertEqual(route_clip([rule("Regex", "Personal", "([a-z]+)+$")],
                                    "text", "a" * 20000 + "!",
                                    "Work", BINS), "Work")


if __name__ == "__main__":
    unittest.main()
