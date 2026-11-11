"""Architecture boundaries that must remain true after the refactoring phase.

Behavior is covered by the regular Qt/integration tests. These guards ensure
future edits cannot silently reintroduce duplicate clipboard copy implementations
or reopen the dual-watcher startup race.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "clipmint"


def module_ast(filename: str) -> ast.Module:
    return ast.parse((APP / filename).read_text(encoding="utf-8"))


def calls_to(tree: ast.AST, attribute: str) -> list[ast.Call]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]


class ArchitectureBoundariesTests(unittest.TestCase):
    def test_saved_history_copy_is_not_reimplemented_by_ui_controllers(self):
        shared = module_ast("history_clipboard_copy.py")
        self.assertTrue(calls_to(shared, "setMimeData"))
        self.assertTrue(calls_to(shared, "refresh_temporary_copy_time"))
        for name in (
            "window_actions.py", "history_controller.py",
            "hotkey_popup_controller.py",
        ):
            with self.subTest(module=name):
                tree = module_ast(name)
                self.assertFalse(calls_to(tree, "setMimeData"))
                self.assertFalse(calls_to(tree, "refresh_temporary_copy_time"))

    def test_bootstrap_acquires_single_instance_before_history_window(self):
        tree = module_ast("app.py")
        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        calls = [
            node for node in ast.walk(main)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"InstanceServer", "ClipMintWindow"}
        ]
        names = {node.func.id: node.lineno for node in calls}
        self.assertLess(names["InstanceServer"], names["ClipMintWindow"])

    def test_database_services_do_not_import_widgets_or_window(self):
        for name in ("history_schema.py", "history_retention.py",
                     "history_search.py", "clip_ingestion.py"):
            with self.subTest(module=name):
                tree = module_ast(name)
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                self.assertFalse(
                    any(s.startswith("PySide6") or s in {"app", "clipmint.app"}
                        for s in imports),
                    f"{name}: a persistence service imports a UI dependency",
                )

    def test_history_schema_and_retention_remain_outside_store_constructor(self):
        store = module_ast("store.py")
        klass = next(node for node in store.body
                     if isinstance(node, ast.ClassDef) and node.name == "ClipStore")
        initializer = next(node for node in klass.body
                           if isinstance(node, ast.FunctionDef)
                           and node.name == "__init__")
        calls = [
            node.func.id for node in ast.walk(initializer)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("initialize_history_schema", calls)
        self.assertIn("HistoryRetentionService", calls)
        self.assertNotIn("sqlite3.connect", calls)

    def test_vault_clipboard_path_remains_distinct_from_saved_history(self):
        # Vault copies must not route through a saved-history operation, which
        # would refresh retention, store a secret, or inadvertently tag it.
        vault = module_ast("vault_controller.py")
        calls = [
            node.func.id for node in ast.walk(vault)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertNotIn("copy_saved_clip", calls)


if __name__ == "__main__":
    unittest.main()
