#!/usr/bin/env python3
"""Create a release-pinned, stdlib-only 227 -> current preview upgrade tool."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def generate(tag: str, version: str, output: Path) -> None:
    if not re.fullmatch(r"clipmint-preview-[0-9]+-[0-9]+", tag):
        raise ValueError("Invalid immutable preview tag")
    if not re.fullmatch(r"0\.6\.0~preview1\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid Debian preview version")
    source = (ROOT / "clipmint" / "package_delta.py").read_text()
    footer = (ROOT / "packaging" / "bootstrap-preview-footer.py").read_text()
    if (footer.count("__CLIPMINT_RELEASE_TAG__") != 1
            or footer.count("__CLIPMINT_RELEASE_VERSION__") != 1):
        raise ValueError("Bootstrap template has missing or duplicate pins")
    footer = footer.replace("__CLIPMINT_RELEASE_TAG__", tag).replace(
        "__CLIPMINT_RELEASE_VERSION__", version
    )
    # Module starts with docstring and future annotations, before the footer.
    result = "#!/usr/bin/python3\n" + source + "\n\n" + footer + "\n"
    ast.parse(result, filename=output.name)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    output.chmod(0o755)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: generate-preview-bootstrap.py TAG VERSION OUTPUT")
    generate(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
