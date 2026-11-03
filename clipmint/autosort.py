"""First-match clipboard routing rules; no evaluation of clipboard-supplied code.

Rules are disabled unless the user opts in. Regex matching uses the third-party
'regex' engine with a hard execution timeout and a limited input slice.
"""
from __future__ import annotations

import re
from typing import Any

import regex

RULE_TYPES = ("Image", "Text", "URL", "Phone", "Keyword", "Regex")
NEVER_CAPTURE = "Never capture"
MAX_PATTERN = 200
REGEX_TEXT_LIMIT = 8192


def validate_rule(value: Any, bins: list[str] | tuple[str, ...]) -> dict:
    """Validate untrusted settings before permitting a rule to run."""
    if not isinstance(value, dict):
        raise ValueError("Rule must be an object")
    mode = value.get("mode")
    pattern = value.get("pattern", "")
    target = value.get("target")
    enabled = value.get("enabled", True)
    if mode not in RULE_TYPES:
        raise ValueError("Unsupported rule type")
    if not isinstance(pattern, str) or len(pattern) > MAX_PATTERN:
        raise ValueError("Rule pattern is too long or invalid")
    if mode in ("Keyword", "Regex") and not pattern.strip():
        raise ValueError("A keyword or pattern is required")
    if not isinstance(enabled, bool):
        raise ValueError("Rule enabled state must be true or false")
    if target not in bins and target != NEVER_CAPTURE:
        raise ValueError("Destination bin no longer exists")
    if mode == "Regex":
        try:
            regex.compile(pattern, regex.IGNORECASE)
        except regex.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
    return {"mode": mode, "pattern": pattern, "target": target, "enabled": enabled}


def rule_matches(rule: dict, kind: str, text: str) -> bool:
    mode = rule["mode"]
    if mode == "Image":
        return kind == "image"
    if kind != "text":
        return False
    if mode == "Text":
        return True
    if mode == "URL":
        return bool(re.search(r"https?://|www\.", text, re.IGNORECASE))
    if mode == "Phone":
        normalized = text.strip()
        return bool(re.fullmatch(r"\+?[\d\s().-]{7,22}", normalized)
                    and sum(ch.isdigit() for ch in normalized) >= 7)
    if mode == "Keyword":
        return rule["pattern"].casefold() in text.casefold()
    if mode == "Regex":
        # Do not silently truncate; anchored patterns could match only because
        # the missing tail makes the truncated string appear to end early.
        if len(text) > REGEX_TEXT_LIMIT:
            return False
        try:
            return bool(regex.search(rule["pattern"], text,
                                     regex.IGNORECASE, timeout=0.02))
        except (regex.error, TimeoutError):
            return False
    return False


def route_clip(
    rules: list[dict],
    kind: str,
    text: str,
    current_bin: str,
    bins: list[str] | tuple[str, ...],
) -> str | None:
    """First enabled matching rule wins. None means deliberately do not capture."""
    if current_bin not in bins:
        current_bin = bins[0] if bins else "Work"
    for candidate in rules:
        try:
            rule = validate_rule(candidate, bins)
            if rule["enabled"] and rule_matches(rule, kind, text):
                return None if rule["target"] == NEVER_CAPTURE else rule["target"]
        except (ValueError, TypeError):
            # Stale/corrupt rules never route clipboard data.
            continue
    return current_bin
