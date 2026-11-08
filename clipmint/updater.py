"""Verified, opt-in ClipMint preview update discovery and staging.

Check the trusted upstream's published GitHub pre-releases. Never execute a
download, run a shell with untrusted metadata, ask for elevated credentials,
or modify /opt/clipmint from this module. Native Mint package management is
responsible for the final system installation and privilege approval.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
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
    r"^clipmint_([0-9]+\.[0-9]+\.[0-9]+[~.]preview[0-9]+\.[0-9]+\.[0-9]+)_amd64\.deb$"
)
SHA_LINE = re.compile(r"^([a-fA-F0-9]{64})\s+\*?([^/\\\s]+)$")
MAX_API_BYTES = 256 * 1024
MAX_CHECKSUM_BYTES = 16 * 1024
MAX_PACKAGE_BYTES = 350 * 1024 * 1024
MAX_DELTA_MANIFEST_BYTES = 8 * 1024
MAX_DELTA_RATIO = 0.85
# Automatic preview updates never download a large .deb. This is a strict
# per-update patch transfer ceiling, not merely a hint to the UI.
MAX_AUTO_DELTA_BYTES = 20 * 1024 * 1024
PREVIEW_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+~preview[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")


class UpdateError(RuntimeError):
    """Release metadata, network, package, or checksum verification failed."""


class SmallerUpdateUnavailable(UpdateError):
    """No trustworthy, affordable delta is available for this installed base."""


@dataclass(frozen=True)
class PreviewUpdate:
    version: str
    filename: str
    package_url: str
    checksum_url: str
    release_url: str
    package_size: int = 0
    delta_manifest_url: str | None = None


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
    except (OSError, ValueError, http.client.HTTPException, EOFError) as exc:
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
        delta_manifests = []
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
            elif name == "DELTA.json":
                delta_manifests.append((url, asset.get("size")))
        if len(packages) != 1 or len(checksums) != 1:
            # Never use an incomplete release; immutable releases are created
            # only after the .deb and SHA256SUMS have been validated in CI.
            continue
        version, filename, url, size = packages[0]
        version = version.replace(".preview", "~preview")
        if (not isinstance(size, int) or size <= 0
                or size > MAX_PACKAGE_BYTES):
            continue
        try:
            package_url = validate_asset_url(url, tag, filename)
            checksum_url = validate_asset_url(checksums[0], tag, "SHA256SUMS")
        except UpdateError:
            continue
        if len(delta_manifests) > 1:
            continue
        delta_manifest_url = None
        if delta_manifests:
            delta_url, delta_size = delta_manifests[0]
            if (type(delta_size) is int
                    and 0 < delta_size <= MAX_DELTA_MANIFEST_BYTES):
                try:
                    delta_manifest_url = validate_asset_url(
                        delta_url, tag, "DELTA.json"
                    )
                except UpdateError:
                    pass  # Full installer remains usable.
        found.append(PreviewUpdate(
            version, filename, package_url, checksum_url,
            f"https://github.com/{OWNER}/{REPOSITORY}/releases/tag/{tag}",
            size, delta_manifest_url,
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


def prune_superseded_previews(folder: Path, retain: Path) -> None:
    """Keep staged and currently installed installers for the next delta.

    Never delete unrelated user files.

    This runs after a successful checksum and Debian-identity verification.
    Stale preview files are large; retain only the installed base and the
    newly staged package instead of accumulating gigabytes of old builds.
    """
    keep = {retain}
    current = installed_version()
    if current and PREVIEW_VERSION.fullmatch(current):
        keep.add(folder / f"clipmint_{current}_amd64.deb")
        keep.add(folder / f"clipmint_{current.replace('~preview', '.preview')}_amd64.deb")
    for old in folder.iterdir():
        if old in keep or not ASSET_PATTERN.fullmatch(old.name):
            continue
        if old.is_symlink():
            # Do not follow or remove links that ClipMint did not create.
            continue
        if old.is_file():
            try:
                old.unlink()
            except OSError:
                # Cache cleanup must not invalidate a verified new package.
                pass


def expected_checksum(raw: bytes, filename: str) -> str:
    """Parse the exact one-file SHA256SUMS generated by our build."""
    try:
        lines = raw.decode("ascii").strip().splitlines()
    except UnicodeDecodeError as exc:
        raise UpdateError("Invalid update checksum encoding") from exc
    if len(lines) != 1:
        raise UpdateError("Update checksum must contain one package")
    match = SHA_LINE.fullmatch(lines[0].strip())
    if (match is None or match.group(2) not in
            {filename, filename.replace(".preview", "~preview")}):
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
    fields = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    if result.returncode or fields != {
        "Package": "clipmint", "Version": version, "Architecture": "amd64",
    }:
        raise UpdateError("Downloaded file is not the expected ClipMint package")



def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def parse_delta_manifest(update: PreviewUpdate, raw: bytes, target_sha: str) -> dict:
    """Only an exact patch tied to two immutable Debian package hashes is usable."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("Invalid delta manifest") from exc
    keys = {"format", "base_version", "base_sha256", "target_version",
            "target_sha256", "patch_name", "patch_sha256", "patch_size"}
    if not isinstance(data, dict) or set(data) != keys:
        raise UpdateError("Unsupported delta manifest")
    base, target = data["base_version"], data["target_version"]
    if (data["format"] not in ("bsdiff4-v1", "tar-content-xz-v1")
            or not isinstance(base, str)
            or not PREVIEW_VERSION.fullmatch(base)
            or target != update.version
            or not PREVIEW_VERSION.fullmatch(target)):
        raise UpdateError("Delta version mismatch")
    for key in ("base_sha256", "target_sha256", "patch_sha256"):
        if not isinstance(data[key], str) or not SHA256_HEX.fullmatch(data[key]):
            raise UpdateError("Invalid delta hash")
    if data["target_sha256"] != target_sha:
        raise UpdateError("Delta target does not match the full package checksum")
    # GitHub's asset store replaces the tilde in Debian versions with a dot.
    extension = ".clipdelta" if data["format"] == "tar-content-xz-v1" else ".bsdiff"
    legacy_name = f"clipmint_delta_from_{base}_to_{target}_amd64{extension}"
    expected_name = legacy_name.replace("~preview", ".preview")
    if data["patch_name"] not in (expected_name, legacy_name):
        raise UpdateError("Unexpected delta filename")
    expected_name = data["patch_name"]
    if not expected_name.startswith("clipmint_delta_from_"):
        raise UpdateError("Unexpected delta filename")
    size = data["patch_size"]
    if (type(size) is not int or size < 32
            or size >= min(MAX_PACKAGE_BYTES, update.package_size * MAX_DELTA_RATIO)):
        raise UpdateError("Delta is not a useful smaller transfer")
    tag = update.release_url.rsplit("/", 1)[-1]
    data["patch_url"] = validate_asset_url(
        f"https://github.com/{OWNER}/{REPOSITORY}/releases/download/{tag}/"
        + expected_name, tag, expected_name
    )
    return data


def download_verified_delta(
    update: PreviewUpdate, target: Path, expected: str, folder: Path,
    *, max_patch_bytes: int | None = None,
) -> bool:
    """Reconstruct only from the exact installed, locally cached .deb.

    Every error returns control to the caller for a full verified download.
    The system-installed application and all clipboard data are untouched.
    """
    if not update.delta_manifest_url or update.package_size <= 0:
        return False
    manifest = parse_delta_manifest(
        update,
        read_bounded(update.delta_manifest_url, MAX_DELTA_MANIFEST_BYTES),
        expected,
    )
    if max_patch_bytes is not None and manifest["patch_size"] > max_patch_bytes:
        return False
    if installed_version() != manifest["base_version"]:
        return False
    base = folder / f"clipmint_{manifest['base_version'].replace('~preview', '.preview')}_amd64.deb"
    if not base.exists():
        base = folder / f"clipmint_{manifest['base_version']}_amd64.deb"
    if (base.is_symlink() or not base.is_file()
            or base.stat().st_size > MAX_PACKAGE_BYTES
            or sha256_file(base) != manifest["base_sha256"]):
        return False
    verify_deb(base, manifest["base_version"])
    patch_fd, patch_name = tempfile.mkstemp(prefix=".clipmint-delta-", dir=folder)
    out_fd, out_name = tempfile.mkstemp(prefix=".clipmint-rebuilt-", dir=folder)
    os.close(out_fd)
    try:
        digest = hashlib.sha256()
        size = 0
        request = Request(
            manifest["patch_url"], headers={"User-Agent": "ClipMint-Updater/0.6"}
        )
        with os.fdopen(patch_fd, "wb") as output:
            try:
                with urlopen(request, timeout=30) as response:
                    if response.status != 200:
                        raise UpdateError("Delta download failed")
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        size += len(block)
                        if size > manifest["patch_size"]:
                            raise UpdateError("Delta is larger than advertised")
                        output.write(block)
                        digest.update(block)
            except (OSError, ValueError, http.client.HTTPException, EOFError) as exc:
                raise UpdateError(f"Cannot download delta: {exc}") from exc
            output.flush()
            os.fsync(output.fileno())
        if (size != manifest["patch_size"]
                or digest.hexdigest() != manifest["patch_sha256"]):
            raise UpdateError("Delta checksum or transfer size mismatch")
        if manifest["format"] == "tar-content-xz-v1":
            # The patch carries exact target tar headers and only changed
            # file contents. Reassemble the official Debian archive byte for
            # byte, then verify its SHA-256 and Debian package identity below.
            from .package_delta import apply_patch, DeltaLayoutError
            try:
                apply_patch(base, Path(patch_name), Path(out_name))
            except (DeltaLayoutError, ValueError, OSError) as exc:
                raise UpdateError("File-aware delta reconstruction failed") from exc
        else:
            with open(patch_name, "rb") as patch_stream:
                header = patch_stream.read(32)
            if header[:8] != b"BSDIFF40" or len(header) != 32:
                raise UpdateError("Invalid bsdiff header")
            encoded_size = int.from_bytes(header[24:32], "little")
            if encoded_size & (1 << 63):
                raise UpdateError("Negative bsdiff output size")
            if encoded_size != update.package_size:
                raise UpdateError("Unexpected reconstructed package size")
            import bsdiff4
            bsdiff4.file_patch(str(base), out_name, patch_name)
        rebuilt = Path(out_name)
        if (rebuilt.stat().st_size != update.package_size
                or sha256_file(rebuilt) != expected):
            raise UpdateError("Reconstructed installer failed checksum verification")
        verify_deb(rebuilt, update.version)
        os.chmod(out_name, 0o600)
        os.replace(out_name, target)
        return True
    finally:
        for name in (patch_name, out_name):
            if os.path.exists(name):
                os.unlink(name)


def download_verified_preview(
    update: PreviewUpdate, *, smaller_only: bool = False,
) -> Path:
    """Stage a verified installer; smaller_only NEVER downloads the full .deb.

    Background calls use smaller_only=True, so a missing/incompatible delta,
    a corrupt patch or a missing base installer can never trigger a 130MB
    fallback. Full packages require a separate, explicit manual choice.
    """
    if not ASSET_PATTERN.fullmatch(update.filename):
        raise UpdateError("Invalid preview package filename")
    if update.filename not in (
        f"clipmint_{update.version}_amd64.deb",
        f"clipmint_{update.version.replace('~preview', '.preview')}_amd64.deb",
    ):
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
            hasher = hashlib.sha256()
            with target.open("rb") as existing:
                while piece := existing.read(1024 * 1024):
                    hasher.update(piece)
            if hasher.hexdigest() == expected:
                verify_deb(target, update.version)
                prune_superseded_previews(folder, target)
                return target
        target.unlink()
    # Always attempt a verified small delta before the full installer.
    # Crucially, the automatic path must NOT fall back to a large .deb.
    try:
        if download_verified_delta(
            update, target, expected, folder,
            max_patch_bytes=MAX_AUTO_DELTA_BYTES if smaller_only else None,
        ):
            prune_superseded_previews(folder, target)
            return target
    except Exception as exc:
        if smaller_only:
            raise SmallerUpdateUnavailable(
                "No usable verified small patch; full package was not downloaded"
            ) from exc
        # Manual users approved a possible full-package fallback.
        pass
    if smaller_only:
        raise SmallerUpdateUnavailable(
            "No verified patch within the 20 MB limit for this installation"
        )

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
            except (OSError, ValueError, http.client.HTTPException, EOFError) as exc:
                raise UpdateError(f"Cannot download ClipMint: {exc}") from exc
            output.flush()
            os.fsync(output.fileno())
        if size == 0 or digest.hexdigest() != expected:
            raise UpdateError("Update checksum verification failed")
        verify_deb(Path(temp_name), update.version)
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, target)
        prune_superseded_previews(folder, target)
        return target
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
