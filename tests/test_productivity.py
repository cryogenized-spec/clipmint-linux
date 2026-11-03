"""Safe local templates, text transformations and manual paste-queue tests."""
import os
import json
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from clipmint.productivity import (
    PasteQueue, TRANSFORMS, render_template, template_fields, transform_text
)


class ProductivityTests(unittest.TestCase):
    def test_placeholder_substitution_is_literal_not_evaluated(self):
        body = "Dear {{customer}}, your parcel {{order}} is ready. {{customer}}"
        self.assertEqual(template_fields(body), ["customer", "order"])
        self.assertEqual(
            render_template(body, {"customer": "__import__('os').system('false')",
                                   "order": "INV123"}),
            "Dear __import__('os').system('false'), your parcel INV123 is ready. "
            "__import__('os').system('false')"
        )
        with self.assertRaises(ValueError):
            render_template(body, {"customer": "A"})
        self.assertEqual(
            render_template("{{customer}}", {"customer": "{{order}}"}),
            "{{order}}"
        )

    def test_common_transformations_keep_original_unchanged(self):
        original = " Bravo \n alpha \n Bravo \n"
        self.assertEqual(transform_text(original, "Strip outer whitespace"),
                         "Bravo \n alpha \n Bravo")
        self.assertEqual(transform_text(original, "Trim each line"),
                         "Bravo\nalpha\nBravo")
        self.assertEqual(transform_text("a\na\nb", "Deduplicate lines"), "a\nb")
        self.assertEqual(transform_text("b\nA", "Sort lines A–Z"), "A\nb")
        self.assertEqual(transform_text("a\n\nb", "Remove empty lines"), "a\nb")
        self.assertEqual(transform_text("HELLO", "Lowercase"), "hello")
        self.assertEqual(transform_text("hello", "Uppercase"), "HELLO")
        self.assertEqual(transform_text("two words", "Title case"), "Two Words")
        self.assertEqual(original, " Bravo \n alpha \n Bravo \n")
        self.assertEqual(len(TRANSFORMS), 12)

    def test_json_and_url_transformations_and_bounded_failures(self):
        raw = '{"a":2,"b": [1,2]}'
        pretty = transform_text(raw, "Format JSON")
        self.assertEqual(json.loads(pretty), json.loads(raw))
        self.assertEqual(transform_text(pretty, "Compact JSON"), '{"a":2,"b":[1,2]}')
        self.assertEqual(transform_text("a & b", "URL encode"), "a%20%26%20b")
        self.assertEqual(transform_text("a%20%26%20b", "URL decode"), "a & b")
        with self.assertRaises(ValueError):
            transform_text("{invalid", "Format JSON")
        with self.assertRaises(ValueError):
            transform_text("A", "Execute Python")
        with self.assertRaises(ValueError):
            transform_text("A"*1_100_000, "Uppercase")

    def test_queue_is_explicit_bounded_and_deduplicated(self):
        queue = PasteQueue(limit=3)
        self.assertTrue(queue.add(12))
        self.assertFalse(queue.add(12))
        self.assertTrue(queue.add(13))
        self.assertEqual(queue.ids(), (12,13))
        self.assertEqual(queue.next_id(), 12)
        self.assertEqual(queue.next_id(), 13)
        self.assertIsNone(queue.next_id())
        for number in (1,2,3):
            queue.add(number)
        with self.assertRaises(ValueError):
            queue.add(4)
        queue.clear()
        self.assertEqual(len(queue), 0)

if __name__ == "__main__":
    unittest.main()
