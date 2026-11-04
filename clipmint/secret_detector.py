"""Detect credential-like clipboard text before storing or displaying it.

This is a best-effort local privacy filter, not a credential security boundary.
False positives are safer than putting actual credentials in SQLite history.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum


class Confidence(IntEnum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class Detection:
    confidence: Confidence = Confidence.NONE
    reasons: list[str] = field(default_factory=list)

    @property
    def is_secret(self) -> bool:
        return self.confidence >= Confidence.MEDIUM

    def _add(self, level: Confidence, reason: str) -> None:
        self.confidence = max(self.confidence, level)
        if reason not in self.reasons:
            self.reasons.append(reason)


PASSWORD_MANAGER_MIME = "x-kde-passwordmanagerhint"
PASSWORD_MANAGER_APPS = (
    "keepassxc", "keepass", "bitwarden", "1password", "enpass",
    "proton pass", "protonpass", "lastpass", "dashlane",
    "gnome-keyring", "seahorse",
)

KNOWN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PEM private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("Twilio key", re.compile(r"\bSK[0-9a-fA-F]{32}\b")),
    ("SendGrid key", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b")),
    ("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("Bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{12,}=*")),
    ("Credentials in URL", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@[^\s/]+")),
)

# Accept plain assignments, JSON-style quoted keys, environment-variable names,
# and text such as "Authorization: Bearer xyz".
KEY_VALUE = re.compile(
    r"(?i)\b(?:password|passwd|passphrase|pwd|secret|token|"
    r"api[_ -]?key|apikey|access[_ -]?key|access[_ -]?token|"
    r"refresh[_ -]?token|private[_ -]?key|client[_ -]?secret|"
    r"authorization|credential[s]?|recovery[_ -]?code|"
    r"seed[_ -]?phrase|otp|2fa|pin)"
    r"\b[\"']?\s*[:=]\s*[\"']?([^\s\"']{3,})"
)
ENV_ASSIGNMENT = re.compile(
    r"(?m)^\s*[\"']?([A-Za-z_][A-Za-z0-9_.-]{2,80})[\"']?\s*[:=]\s*[\"']?([^\s\"']{4,})"
)
SENSITIVE_ENV_ENDINGS = (
    "PASSWORD", "PASSPHRASE", "SECRET", "TOKEN", "API_KEY",
    "PRIVATE_KEY", "ACCESS_KEY", "REFRESH_KEY", "STATE_KEY",
    "ENCRYPTION_KEY", "SIGNING_KEY", "DATABASE_URL", "CONNECTION_STRING",
)
CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX = re.compile(r"^[0-9a-fA-F]+$")
URL_OR_PATH = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|/|~/|\.{1,2}/|[A-Za-z]:\\)", re.I)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def luhn_ok(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, ch in enumerate(reversed(digits)):
        number = int(ch)
        if index % 2:
            number = number * 2 - 9 if number > 4 else number * 2
        total += number
    return total % 10 == 0


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    return -sum((count / len(value)) * math.log2(count / len(value))
                for count in counts.values())


def looks_random(token: str) -> Confidence:
    """Classify only a *bare*, single, whitespace-free token."""
    size = len(token)
    if not 8 <= size <= 512:
        return Confidence.NONE
    if (UUID.fullmatch(token) or EMAIL.fullmatch(token) or IPV4.fullmatch(token)
            or URL_OR_PATH.match(token) or token.isalpha() or token.isdigit()):
        return Confidence.NONE
    entropy = shannon_entropy(token)
    if HEX.fullmatch(token) and size >= 32 and entropy >= 3.2:
        return Confidence.MEDIUM  # Includes hex keys and hashes: intentional caution
    classes = sum((
        any(c.islower() for c in token),
        any(c.isupper() for c in token),
        any(c.isdigit() for c in token),
        any(not c.isalnum() for c in token),
    ))
    if size >= 20 and entropy >= 4.0 and classes >= 3:
        return Confidence.MEDIUM
    if 8 <= size <= 32 and classes >= 3 and entropy >= 3.0:
        if classes == 4 or (size >= 14 and entropy >= 3.3):
            return Confidence.MEDIUM
        return Confidence.LOW
    return Confidence.NONE


def detect_secret(
    text: str,
    mime_targets: list[str] | tuple[str, ...] | None = None,
    source_app: str | None = None,
) -> Detection:
    result = Detection()
    # Check hints FIRST, even when no textual representation is supplied.
    if mime_targets and any(target.lower() == PASSWORD_MANAGER_MIME
                            or any(app in target.lower() for app in PASSWORD_MANAGER_APPS)
                            for target in mime_targets):
        result._add(Confidence.HIGH, "password manager clipboard hint")
    if source_app and any(app in source_app.lower() for app in PASSWORD_MANAGER_APPS):
        result._add(Confidence.HIGH, "password manager source hint")
    if not text or not text.strip():
        return result

    for name, pattern in KNOWN_PATTERNS:
        if pattern.search(text):
            result._add(Confidence.HIGH, name)
    if KEY_VALUE.search(text):
        result._add(Confidence.MEDIUM, "credential assignment")
    for match in ENV_ASSIGNMENT.finditer(text):
        key = match.group(1).upper().replace("-", "_").replace(".", "_")
        if any(key == suffix or key.endswith("_" + suffix)
               for suffix in SENSITIVE_ENV_ENDINGS):
            result._add(Confidence.MEDIUM, "credential environment variable")
            break
    for candidate in CARD_CANDIDATE.finditer(text):
        if luhn_ok(candidate.group()):
            result._add(Confidence.HIGH, "payment card checksum")
            break

    single = text.strip()
    if not any(ch.isspace() for ch in single):
        level = looks_random(single)
        if level:
            result._add(level, "random-looking token")
    return result


def mask(_text: str, reveal: int = 0) -> str:
    """Fixed-length placeholder; never put the original value in a list label."""
    # Any intentional reveal must use a separate, explicitly authorised vault UI.
    return "\N{BULLET}" * 12
