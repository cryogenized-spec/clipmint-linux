"""Standalone, stdlib-only small-data upgrade entry point.

The GitHub release publisher appends this to clipmint/package_delta.py after
substituting the exact immutable target tag and package version. It NEVER
installs anything, invokes sudo, runs pip/apt, or downloads a full installer.
"""

def _bootstrap_sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def _bootstrap_fetch(url, size_limit):
    from urllib.request import Request, urlopen
    request = Request(url, headers={"User-Agent": "ClipMint-Bootstrap/0.6"})
    with urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise ValueError("Official release server did not return HTTP 200")
        data = response.read(size_limit + 1)
    if len(data) > size_limit:
        raise ValueError("Upstream response exceeds safety limit")
    return data


def _bootstrap_identity(path, version):
    result = subprocess.run(
        ["/usr/bin/dpkg-deb", "-f", str(path), "Package", "Version",
         "Architecture"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    fields = {}
    for row in result.stdout.splitlines():
        key, separator, value = row.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    if result.returncode or fields != {
        "Package": "clipmint", "Version": version, "Architecture": "amd64"
    }:
        raise ValueError("Installer Debian package identity does not match")


def _bootstrap_run():
    import os
    import re

    # Values inserted by the verified main-branch release publisher.
    tag = "__CLIPMINT_RELEASE_TAG__"
    version = "__CLIPMINT_RELEASE_VERSION__"
    base_version = "0.6.0~preview1.227.1"
    base_name = "clipmint_0.6.0.preview1.227.1_amd64.deb"
    base_name_alt = "clipmint_0.6.0~preview1.227.1_amd64.deb"
    target_name = "clipmint_" + version.replace("~preview", ".preview") + "_amd64.deb"
    root = ("https://github.com/cryogenized-spec/clipmint-linux/"
            "releases/download/" + tag + "/")
    if not re.fullmatch(r"clipmint-preview-[0-9]+-[0-9]+", tag):
        raise ValueError("Invalid embedded release tag")
    if not re.fullmatch(r"0\.6\.0~preview1\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid embedded target version")
    print("ClipMint verified small-data bootstrap: " + base_version + " → " + version)
    print("This tool will NOT download the full installer or install software.")
    home = Path.home()
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    cache_root = (Path(xdg_cache) if xdg_cache and Path(xdg_cache).is_absolute()
                  else home / ".cache")
    cache_dir = cache_root / "clipmint" / "updates"
    old = None
    # Do not enumerate user folders. Only exact filenames, no symlinks.
    for location in (cache_dir, home / "Downloads"):
        for name in (base_name, base_name_alt):
            candidate = location / name
            if (candidate.is_symlink() or not candidate.is_file()
                    or not 0 < candidate.stat().st_size <= MAX_DEB):
                continue
            old = candidate
            break
        if old is not None:
            break
    if old is None:
        raise ValueError(
            "Original 227.1 installer not found in Downloads or ClipMint cache. "
            "No patch downloaded."
        )
    print("Found original installer: " + str(old))
    checksum = _bootstrap_fetch(root + "SHA256SUMS", 2048)
    import re as _re
    expected_line = _re.fullmatch(
        rb"([a-fA-F0-9]{64})  " + target_name.encode() + rb"\r?\n?",
        checksum,
    )
    if expected_line is None:
        raise ValueError("Official target SHA256SUMS does not match this release")
    target_hash = expected_line.group(1).decode("ascii").lower()
    manifest = json.loads(_bootstrap_fetch(root + "DELTA-227.json", 8192))
    required = {"format", "base_version", "base_sha256", "target_version",
                "target_sha256", "patch_name", "patch_sha256", "patch_size"}
    patch_name = manifest.get("patch_name")
    if (set(manifest) != required or manifest["format"] != FORMAT
            or manifest["base_version"] != base_version
            or manifest["target_version"] != version
            or manifest["target_sha256"] != target_hash
            or not isinstance(patch_name, str)
            or not _re.fullmatch(
                r"clipmint_delta_from_0\.6\.0\.preview1\.227\.1_to_"
                r"0\.6\.0\.preview1\.[0-9]+\.[0-9]+_amd64\.clipdelta",
                patch_name,
            )
            or not isinstance(manifest["patch_size"], int)
            or not 32 <= manifest["patch_size"] <= MAX_PATCH
            or not all(_re.fullmatch("[a-f0-9]{64}", manifest[k])
                       for k in ("base_sha256", "patch_sha256", "target_sha256"))):
        raise ValueError("Invalid official 227 bootstrap delta manifest")
    if _bootstrap_sha256(old) != manifest["base_sha256"]:
        raise ValueError("Existing 227 installer checksum differs from official base")
    _bootstrap_identity(old, base_version)
    patch_bytes = manifest["patch_size"]
    print("Verified base. Patch transfer: " +
          f"{patch_bytes / 1024 / 1024:.2f} MiB (maximum 20 MiB).")
    try:
        answer = input("Download the small verified patch? [y/N] ").strip().lower()
    except EOFError:
        return
    if answer not in ("y", "yes"):
        print("Cancelled. No patch downloaded.")
        return
    patch_data = _bootstrap_fetch(root + patch_name, patch_bytes)
    if (len(patch_data) != patch_bytes
            or hashlib.sha256(patch_data).hexdigest()
            != manifest["patch_sha256"]):
        raise ValueError("Patch size/hash verification failed")
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if cache_dir.is_symlink():
        raise ValueError("Refusing a symlink update cache")
    import tempfile
    with tempfile.TemporaryDirectory(prefix=".clipmint-upgrade-", dir=cache_dir) as tmp:
        temp = Path(tmp)
        patch_path = temp / patch_name
        output_path = temp / target_name
        patch_path.write_bytes(patch_data)
        print("Reconstructing installer from verified old package (offline)...")
        apply_patch(old, patch_path, output_path)
        if (_bootstrap_sha256(output_path) != target_hash
                or output_path.stat().st_size > MAX_DEB):
            raise ValueError("Rebuilt installer does not match official SHA-256")
        _bootstrap_identity(output_path, version)
        destination = cache_dir / target_name
        if destination.is_symlink():
            raise ValueError("Refusing to overwrite a symlink")
        if destination.exists():
            if _bootstrap_sha256(destination) != target_hash:
                raise ValueError("Existing staged installer differs; not overwriting")
        else:
            os.chmod(output_path, 0o600)
            os.replace(output_path, destination)
    print("✓ Reconstructed full installer verified against official SHA-256.")
    print("✓ Saved to: " + str(destination))
    print("Nothing was installed. Open this .deb in Linux Mint Package Installer")
    print("and approve the upgrade, then fully quit and restart ClipMint.")


if __name__ == "__main__":
    try:
        _bootstrap_run()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            DeltaLayoutError) as failure:
        print("Bootstrap stopped safely: " + str(failure))
        raise SystemExit(1) from None
