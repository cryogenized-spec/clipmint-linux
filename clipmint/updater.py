"""Verified, opt-in ClipMint preview update discovery and staging.

Check the trusted upstream's published GitHub pre-releases. Never execute a
download, run a shell with untrusted metadata, ask for elevated credentials,
or modify /opt/clipmint from this module. Native Mint package management is
responsible for the final system installation and privilege approval.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

OWNER = "cryogenized-spec"
REPOSITORY = "clipmint-linux"
API_URL = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/releases?per_page=20"
RELEASE_PREFIX = "clipmint-preview-"
ASSET_PATTERN = re.compile(
    r"^clipmint_([0-9]+\.[0-9]+\.[0-9]+~preview[0-9]+\.[0-9]+\.[0-9]+)_amd64\.deb$"
)
SHA_LINE = re.compile(r"^([a-fA-F0-9]{64})\s+\*?([^/\\\s]+)$")
MAX_API_BYTES = 256 * 1024
MAX_CHECKSUM_BYTES = 16 * 1024
MAX_PACKAGE_BYTES = 350 * 1024 * 1024


class UpdateError(RuntimeError):
    """Release metadata, network, package, or checksum verification failed."""


@dataclass(frozen=True)
class PreviewUpdate:
    version: str
    filename: str
    package_url: str
    checksum_url: str
    release_url: str


def validate_asset_url(url: str, tag: str, filename: str) -> str:
    """Accept only canonical HTTPS assets of our exact upstream release."""
    target = urlparse(url)
    expected = f"/{OWNER}/{REPOSITORY}/releases/download/{tag}/{filename}"
    if (target.scheme != "https" or target.netloc != "github.com"
            or target.path != expected or target.params or target.query
            or target.fragment):
        raise UpdateError("Unexpected update download address")
    return url


def read_bounded(url: str, max_bytes: int) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "ClipMint-Updater/0.6",
                 "Accept": "application/vnd.github+json" if url == API_URL
                 else "application/octet-stream"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise UpdateError(f"Update server returned HTTP {response.status}")
            data = response.read(max_bytes + 1)
    except (OSError, ValueError) as exc:
        raise UpdateError(f"Cannot retrieve updates: {exc}") from exc
    if len(data) > max_bytes:
        raise UpdateError("Update metadata exceeded permitted size")
    return data


def parse_preview_releases(raw: bytes) -> list[PreviewUpdate]:
    try:
        releases = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("Invalid upstream release metadata") from exc
    if not isinstance(releases, list):
        raise UpdateError("Invalid upstream release response")
    found = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") is not False:
            continue
        tag = release.get("tag_name")
        if (not isinstance(tag, str)
                or not re.fullmatch(r"clipmint-preview-[0-9]+-[0-9]+", tag)
                or release.get("prerelease") is not True):
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        packages = []
        checksums = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name, url = asset.get("name"), asset.get("browser_download_url")
            if not isinstance(name, str) or not isinstance(url, str):
                continue
            match = ASSET_PATTERN.fullmatch(name)
            if match:
                packages.append((match.group(1), name, url, asset.get("size")))
            elif name == "SHA256SUMS":
                checksums.append(url)
        if len(packages) != 1 or len(checksums) != 1:
            # Never use an incomplete release; immutable releases are created
            # only after the .deb and SHA256SUMS have been validated in CI.
            continue
        version, filename, url, size = packages[0]
        if (not isinstance(size, int) or size <= 0
                or size > MAX_PACKAGE_BYTES):
            continue
        try:
            package_url = validate_asset_url(url, tag, filename)
            checksum_url = validate_asset_url(checksums[0], tag, "SHA256SUMS")
        except UpdateError:
            continue
        found.append(PreviewUpdate(
            version, filename, package_url, checksum_url,
            f"https://github.com/{OWNER}/{REPOSITORY}/releases/tag/{tag}",
        ))
    return found


def installed_version() -> str | None:
    try:
        result = subprocess.run(
            ["/usr/bin/dpkg-query", "-W", "-f=${Version}", "clipmint"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = result.stdout.strip()
    return version if result.returncode == 0 and version else None


def version_is_newer(candidate: str, current: str) -> bool:
    """Use Debian version semantics, not lexical string comparisons."""
    if not ASSET_PATTERN.fullmatch(f"clipmint_{candidate}_amd64.deb"):
        raise UpdateError("Unsupported preview version")
    try:
        result = subprocess.run(
            ["/usr/bin/dpkg", "--compare-versions", current, "lt", candidate],
            capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError("Could not compare installed package versions") from exc
    if result.returncode not in (0, 1):
        raise UpdateError("Debian package version comparison failed")
    return result.returncode == 0


def check_for_preview_update() -> PreviewUpdate | None:
    """Return a newer, fully published preview; never a downgrade."""
    current = installed_version()
    if current is None:
        # A development checkout should not prompt to replace the system app.
        return None
    releases = parse_preview_releases(read_bounded(API_URL, MAX_API_BYTES))
    latest = None
    for release in releases:
        if not version_is_newer(release.version, current):
            continue
        if latest is None or version_is_newer(release.version, latest.version):
            latest = release
    return latest


def cached_updates_dir() -> Path:
    root = os.environ.get("XDG_CACHE_HOME")
    base = Path(root) if root and Path(root).is_absolute() else Path.home() / ".cache"
    folder = base / "clipmint" / "updates"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if folder.is_symlink():
        raise UpdateError("Update cache cannot be a symlink")
    return folder


def expected_checksum(raw: bytes, filename: str) -> str:
    """Parse the exact one-file SHA256SUMS generated by our build."""
    try:
        lines = raw.decode("ascii").strip().splitlines()
    except UnicodeDecodeError as exc:
        raise UpdateError("Invalid update checksum encoding") from exc
    if len(lines) != 1:
        raise UpdateError("Update checksum must contain one package")
    match = SHA_LINE.fullmatch(lines[0].strip())
    if match is None or match.group(2) != filename:
        raise UpdateError("Update checksum does not match package filename")
    return match.group(1).lower()


def verify_deb(path: Path, version: str) -> None:
    """Reject any file whose internal Debian identity differs from metadata."""
    try:
        result = subprocess.run(
            ["/usr/bin/dpkg-deb", "-f", str(path),
             "Package", "Version", "Architecture"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError("Could not inspect downloaded Debian package") from exc
    fields = [part.strip() for part in result.stdout.splitlines()]
    if result.returncode or fields != ["clipmint", version, "amd64"]:
        raise UpdateError("Downloaded file is not the expected ClipMint package")


def download_verified_preview(update: PreviewUpdate) -> Path:
    """Download into a private cache, atomically accept only verified .deb."""
    if not ASSET_PATTERN.fullmatch(update.filename):
        raise UpdateError("Invalid preview package filename")
    if update.filename != f"clipmint_{update.version}_amd64.deb":
        raise UpdateError("Update version mismatch")
    tag = urlparse(update.release_url).path.rsplit("/", 1)[-1]
    validate_asset_url(update.package_url, tag, update.filename)
    validate_asset_url(update.checksum_url, tag, "SHA256SUMS")
    expected = expected_checksum(
        read_bounded(update.checksum_url, MAX_CHECKSUM_BYTES),
        update.filename,
    )
    folder = cached_updates_dir()
    target = folder / update.filename
    if target.is_file() and not target.is_symlink():
        if target.stat().st_size <= MAX_PACKAGE_BYTES:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest == expected:
                verify_deb(target, update.version)
                return target
        target.unlink()
    request = Request(
        update.package_url, headers={"User-Agent": "ClipMint-Updater/0.6"}
    )
    fd, temp_name = tempfile.mkstemp(prefix=".clipmint-preview-", dir=folder)
    try:
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "wb") as output:
            try:
                with urlopen(request, timeout=30) as response:
                    if response.status != 200:
                        raise UpdateError("Update package download failed")
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_PACKAGE_BYTES:
                            raise UpdateError("Update package exceeds size limit")
                        digest.update(chunk)
                        output.write(chunk)
            except (OSError, ValueError) as exc:
                raise UpdateError(f"Cannot download ClipMint: {exc}") from exc
            output.flush()
            os.fsync(output.fileno())
        if size == 0 or digest.hexdigest() != expected:
            raise UpdateError("Update checksum verification failed")
        verify_deb(Path(temp_name), update.version)
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, target)
        return target
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
