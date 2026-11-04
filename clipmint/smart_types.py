"""Local heuristic clipboard type recognition for ClipMint Autosort.

Only classification and routing hints live here. No network requests, command
execution, contact lookup, file opening, or secret persistence is performed.
Unknown or ambiguous content falls back to ordinary text/current collection.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePath
from urllib.parse import parse_qsl, urlsplit


@dataclass(frozen=True)
class SmartType:
    key: str
    label: str
    bin: str
    private: bool = False


# Public defaults group 30 specific content classes into navigable archives.
# Sensitive categories NEVER go into a normal history collection.
SMART_TYPES: tuple[SmartType, ...] = (
    SmartType("passwords", "Passwords & master keys", "Never capture", True),
    SmartType("otp", "One-time passcodes (OTP / 2FA)", "Never capture", True),
    SmartType("api-keys", "API keys & bearer tokens", "Never capture", True),
    SmartType("payment-cards", "Payment cards (PAN / CVV)", "Never capture", True),
    SmartType("banking", "Bank routing & account numbers", "Never capture", True),
    SmartType("tracking-urls", "Tracking / affiliate URLs", "Web"),
    SmartType("web-urls", "Web URLs", "Web"),
    SmartType("crypto-wallets", "Cryptocurrency wallet addresses", "Finance"),
    SmartType("email", "Email addresses", "Contacts"),
    SmartType("phone", "Phone numbers", "Contacts"),
    SmartType("postal-addresses", "Postal addresses", "Contacts"),
    SmartType("package-tracking", "Package tracking numbers", "Utilities"),
    SmartType("calendar-dates", "Calendar timestamps & dates", "Utilities"),
    SmartType("local-paths", "Local filesystem paths", "Utilities"),
    SmartType("os-files", "OS file & directory references", "Media"),
    SmartType("images", "Raster images & screenshots", "Media"),
    SmartType("svg", "SVG vectors", "Media"),
    SmartType("colors", "Colour codes", "Media"),
    SmartType("json", "JSON payloads", "Data"),
    SmartType("yaml-xml", "YAML & XML documents", "Data"),
    SmartType("tables", "Tabular CSV / TSV", "Data"),
    SmartType("source-code", "Source code snippets", "Development"),
    SmartType("cli", "Terminal & CLI commands", "Development"),
    SmartType("logs", "Error logs & stack traces", "Development"),
    SmartType("hashes", "Cryptographic hashes & checksums", "Development"),
    SmartType("math", "Mathematics & LaTeX", "Utilities"),
    SmartType("templates", "Canned templates & placeholders", "Templates"),
    SmartType("markdown", "Markdown snippets", "Writing"),
    SmartType("rich-text", "Rich text / HTML", "Writing"),
    SmartType("plain-text", "Plain text & paragraphs", "Writing"),
)
TYPE_BY_KEY = {item.key: item for item in SMART_TYPES}
DEFAULT_BINS = tuple(dict.fromkeys(
    item.bin for item in SMART_TYPES if not item.private and item.bin != "Never capture"
))
PRIVATE_KEYS = frozenset(item.key for item in SMART_TYPES if item.private)
TRACKING_PARAMS = frozenset((
    "fbclid", "gclid", "dclid", "msclkid", "igshid", "ref", "ref_src",
    "affiliate", "aff_id", "aff", "mc_cid", "mc_eid", "yclid", "twclid",
))
URL = re.compile(r"(?i)^(?:https?://|www\.)[^\s<>]+$")
EMAIL = re.compile(r"(?i)^[a-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@[a-z0-9.-]+\.[a-z]{2,24}$")
PHONE = re.compile(r"^\+?[\d\s().-]{7,24}$")
OTP = re.compile(r"^\d{6,8}$")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
IBAN = re.compile(r"(?<!\w)[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?!\w)", re.I)
SWIFT_CONTEXT = re.compile(r"(?i)\b(?:swift|bic|iban|sort[\s-]?code|routing[\s-]?number|account[\s-]?(?:number|no|nr)|branch[\s-]?code)\s*[:=#-]?\s*\S+")
API_CONTEXT = re.compile(
    r"(?i)(?<![\w-])(?:password|passphrase|passwd|pwd|client[_ -]?secret|"
    r"api[_ -]?key|access[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"private[_ -]?key|secret[_ -]?key|auth(?:orization)?|bearer)\s*"
    r"(?:[\"']?\s*[:=]\s*[\"']?\s*|\s+)(\S{3,})"
)
KNOWN_API = re.compile(
    r"(?i)\b(?:github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9_]{30,}|"
    r"glpat-[A-Za-z0-9_-]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|"
    r"AIza[A-Za-z0-9_-]{35}|AKIA[A-Z0-9]{16}|"
    r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}|"
    r"npm_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9-]{10,})\b"
)
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
PEM = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----", re.I)
BASE64 = re.compile(r"^[A-Za-z0-9+/]{38,}={0,2}$")
HEX = re.compile(r"^[0-9a-fA-F]{32,128}$")
HASH_CONTEXT = re.compile(r"(?i)\b(?:sha(?:1|256|512)?|md5|checksum|digest|git\s+commit)\b")
BITCOIN = re.compile(r"^(?:bc1[ac-hj-np-z02-9]{25,85}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$", re.I)
ETHEREUM = re.compile(r"^0x[a-f0-9]{40}$", re.I)
SOLANA = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
WIF = re.compile(r"^[5KL][1-9A-HJ-NP-Za-km-z]{50,51}$")
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
CSS_COLOR = re.compile(r"(?i)^(?:rgba?|hsla?)\s*\([^()]{3,90}\)$")
LOG = re.compile(r"(?im)(?:^Traceback \(most recent call last\):|"
                 r"^\s*at\s+\S+\s+\(|^\s*File \".+\", line \d+|"
                 r"^\s*(?:DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\s*[:\[\s])")
SOURCE_CODE = re.compile(r"(?m)^\s*(?:def\s+\w+\s*\(|class\s+\w+[\(:]|"
                         r"from\s+\w+\s+import\s+|import\s+[\w.]+\s*$|"
                         r"(?:async\s+)?function\s+\w+\s*\(|"
                         r"(?:const|let|var)\s+\w+\s*=|"
                         r"fn\s+\w+\s*\(|(?:pub\s+)?(?:struct|enum|impl)\s+\w+|"
                         r"#include\s*[<\"]|package\s+\w+;)")
COMMAND = re.compile(r"(?i)^\s*(?:sudo|git|npm|npx|pnpm|yarn|pip|python\d?|"
                     r"node|cargo|rustc|go|docker|podman|kubectl|helm|"
                     r"curl|wget|ssh|scp|rsync|apt|apt-get|systemctl|"
                     r"journalctl|ls|cd|mkdir|grep|find|sed|awk|"
                     r"chmod|chown|export|bash|zsh|pwsh|powershell|"
                     r"ffmpeg)\s+[-./~'\w]")
MARKDOWN = re.compile(r"(?m)^\s*(?:#{1,6}\s+\S+|[-*+]\s+\S+|"
                      r"\d+\.\s+\S+|>\s+\S+|[~\x60]{3})")
MATH = re.compile(r"\\(?:frac|int|sum|sqrt|begin|alpha|beta|lim|pi|theta)\b|"
                  r"^\s*\$\$.+\$\$\s*$|^\s*[xy]\s*=\s*[\w\d+\-*/()^. ]{3,}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ][0-2]\d:[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?$")
EPOCH = re.compile(r"^\d{10}(?:\d{3})?$")
TRACKING = re.compile(r"(?i)^(?:1Z[0-9A-Z]{16}|[A-Z]{2}\d{9}[A-Z]{2})$")
TRACKING_CONTEXT = re.compile(r"(?i)\b(?:fedex|dhl|ups|usps|courier|tracking|waybill|awb)\b")
POSTAL = re.compile(r"(?im)^\s*\d{1,6}[A-Za-z]?\s+[\w.' -]{4,80}"
                    r"\b(?:st(?:reet)?|rd|road|ave(?:nue)?|lane|ln|drive|dr|"
                    r"boulevard|blvd|crescent|close|way)\b[^\n]*(?:\n|,)")
PATH = re.compile(r"^(?:/[^/\s]|~/|\.{1,2}/|[A-Z]:\\)[^\n]{1,500}$", re.I)
TEMPLATE = re.compile(r"\{\{\s*[A-Za-z_]\w{0,64}\s*\}\}|\$\{[A-Za-z_]\w{0,64}\}")
SVG = re.compile(r"(?is)^\s*(?:<\?xml[^>]*>\s*)?<svg\b")
XML = re.compile(r"(?is)^\s*(?:<\?xml\b|<(?!html\b)[a-z][\w:.-]*(?:\s+[^<>]*)?>)")
YAML = re.compile(r"(?m)^\s*[\w.-]{2,50}:\s*\S.*$", re.M)
PAN_CVV = re.compile(r"(?i)\b(?:cvv|cvc|security\s*code)\s*[:=#-]?\s*\d{3,4}\b")


def _entropy(value: str) -> float:
    counts = Counter(value)
    n = len(value)
    return -sum((count / n) * math.log2(count / n) for count in counts.values()) if n else 0


def _luhn(value: str) -> bool:
    digits = [int(x) for x in value if x.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    return sum((int(x) * 2 - 9 if int(x) > 4 else int(x) * 2)
               if position % 2 else int(x)
               for position, x in enumerate(reversed(digits))) % 10 == 0


def _has_table(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 500:
        return False
    for delimiter in ("\t", ",", ";"):
        if sum(delimiter in line for line in lines[:4]) < 2:
            continue
        try:
            rows = list(csv.reader(io.StringIO("\n".join(lines[:20])),
                                   delimiter=delimiter))
        except csv.Error:
            continue
        if rows and 2 <= len(rows[0]) <= 50 and all(
            len(row) == len(rows[0]) for row in rows[1:]
        ):
            return True
    return False


def classify_smart(
    kind: str, text: str, formats: dict[str, bytes] | None = None,
) -> str | None:
    """Return one of 30 smart-type IDs, or None for unsupported/empty content.

    Ordering is intentional: private credentials have priority; high-specificity
    formats are classified before the generic text fallback.
    """
    if kind == "files":
        return "os-files"
    if kind == "image":
        return "images"
    if kind != "text" or not isinstance(text, str) or not text.strip():
        return None
    value = text.strip()
    # Bounded heuristics; the separate privacy filter also inspects text
    # before the clipboard item is admitted into history.
    if len(value) > 262144:
        return "plain-text"
    sample = value[:262144]
    if PAN_CVV.search(sample) or any(_luhn(m.group()) for m in CARD.finditer(sample)):
        return "payment-cards"
    if IBAN.search(sample) or SWIFT_CONTEXT.search(sample):
        return "banking"
    if PEM.search(sample) or WIF.fullmatch(value) or (
        API_CONTEXT.search(sample) and re.search(
            r"(?i)\b(?:password|passwd|passphrase|pwd|master|private[_ -]?key|"
            r"client[_ -]?secret|secret[_ -]?key)\b", sample
        )
    ):
        return "passwords"
    if KNOWN_API.search(sample) or BEARER.search(sample) or JWT.search(sample) or (
        API_CONTEXT.search(sample) and re.search(
            r"(?i)\b(?:token|api[_ -]?key|access[_ -]?key|auth(?:orization)?|bearer)\b", sample
        )
    ):
        return "api-keys"
    # A bare 6-8-digit number is ambiguous (often an invoice or date);
    # opt for privacy rather than retaining a possible one-time code.
    if OTP.fullmatch(value):
        return "otp"
    if (len(value) in range(12, 129) and not any(ch.isspace() for ch in value)
            and not EMAIL.fullmatch(value) and not URL.fullmatch(value)
            and not PATH.fullmatch(value) and not HEX_COLOR.fullmatch(value)
            and not ETHEREUM.fullmatch(value) and not BITCOIN.fullmatch(value)
            and not TRACKING.fullmatch(value)
            and not HASH_CONTEXT.search(value)
            and _entropy(value) >= (4.15 if len(value) >= 24 else 3.4)
            and sum((any(c.islower() for c in value),
                     any(c.isupper() for c in value),
                     any(c.isdigit() for c in value),
                     any(not c.isalnum() for c in value))) >= 3):
        return "passwords"
    if HEX.fullmatch(value) and len(value) >= 40 and not HASH_CONTEXT.search(value):
        # A bare hash may also be a random authentication key: exclude rather
        # than making a risky assumption about its purpose.
        return "passwords"
    if URL.fullmatch(value):
        normalized = value if value.lower().startswith(("http://", "https://")) \
            else "https://" + value
        parts = urlsplit(normalized)
        params = parse_qsl(parts.query, keep_blank_values=True)
        if any(key.lower().startswith("utm_") or key.lower() in TRACKING_PARAMS
               for key, _ in params):
            return "tracking-urls"
        return "web-urls"
    if ETHEREUM.fullmatch(value) or BITCOIN.fullmatch(value) or SOLANA.fullmatch(value):
        return "crypto-wallets"
    if EMAIL.fullmatch(value):
        return "email"
    if (PHONE.fullmatch(value)
            and 7 <= sum(ch.isdigit() for ch in value) <= 15
            and not EPOCH.fullmatch(value)):
        return "phone"
    if POSTAL.search(value) and len(value.splitlines()) >= 2:
        return "postal-addresses"
    if TRACKING.fullmatch(value) or (TRACKING_CONTEXT.search(sample)
                                    and re.search(r"(?i)[A-Z0-9]{10,35}", sample)):
        return "package-tracking"
    if ISO_DATE.fullmatch(value) or EPOCH.fullmatch(value) or re.search(
        r"(?i)\b(?:tomorrow|next\s+(?:monday|tuesday|wednesday|thursday|"
        r"friday|saturday|sunday))\s+(?:at\s+)?\d{1,2}:\d{2}\b", value
    ):
        return "calendar-dates"
    if PATH.fullmatch(value):
        return "local-paths"
    if SVG.search(sample):
        return "svg"
    if HEX_COLOR.fullmatch(value) or CSS_COLOR.fullmatch(value):
        return "colors"
    if value.startswith(("{", "[")):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, (dict, list)):
                return "json"
        except (json.JSONDecodeError, ValueError):
            # Preserve malformed JSON-like documents in a data collection
            # for later validation. Do not execute or parse as code.
            if re.match(r"^\s*[\{\[]\s*[\"'\[\{]", value):
                return "json"
    if XML.search(sample) or len(YAML.findall(sample)) >= 2:
        return "yaml-xml"
    if _has_table(value):
        return "tables"
    if LOG.search(sample):
        return "logs"
    if SOURCE_CODE.search(sample):
        return "source-code"
    if "\n" not in value and COMMAND.match(value):
        return "cli"
    if HASH_CONTEXT.search(sample) and HEX.search(value.split()[-1]):
        return "hashes"
    if MATH.search(value):
        return "math"
    if TEMPLATE.search(sample):
        return "templates"
    if MARKDOWN.search(sample):
        return "markdown"
    if formats and any("text/html" == name.lower() and body
                       for name, body in formats.items()):
        return "rich-text"
    return "plain-text"


def sensitive_clipboard_text(text: str) -> bool:
    """Privacy-first gate, independent of whether Autosort is toggled on."""
    return classify_smart("text", text) in PRIVATE_KEYS


def default_smart_rules() -> list[dict]:
    """All thirty visible editable rules, ordered by classification priority."""
    return [
        {"mode": "Smart", "pattern": item.key,
         "target": item.bin, "enabled": True}
        for item in SMART_TYPES
    ]
