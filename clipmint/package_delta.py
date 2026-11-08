"""Byte-exact, file-aware differential transport for ClipMint Debian archives.

Debian's xz-compressed data.tar changes almost completely when one source
file changes. Diffing the compressed .deb is therefore expensive and rarely
useful. This transport reuses unchanged tar *file bodies*, carries the exact
new tar headers and changed bodies, then re-creates the exact xz and ar bytes.
The system dpkg-deb tool is used only to read trusted cached base tar data;
no extraction to disk, shell commands, or package installation occurs.

A candidate is released ONLY if application reproduces the SHA256 of the
official new Debian installer. The updater separately checks the release
manifest, cached old .deb identity, downloaded patch digest and new .deb.
"""
from __future__ import annotations

import base64
import bz2
import hashlib
import io
import json
import lzma
import os
import subprocess
from pathlib import Path
import tarfile
import zipfile
import tempfile
import zlib


FORMAT = "tar-content-xz-v1"
MAX_DEB = 350 * 1024 * 1024
MAX_RAW_TAR = 1024 * 1024 * 1024
MAX_META = 16 * 1024 * 1024
MAX_PATCH = 20 * 1024 * 1024
MAX_BSDIFF_FILE = 64 * 1024 * 1024


class DeltaLayoutError(ValueError):
    """Package cannot be reproduced by the safe, supported xz layout."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode(value: str) -> bytes:
    if not isinstance(value, str):
        raise DeltaLayoutError("Invalid delta bytes")
    return base64.b64decode(value, validate=True)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ar_members(data: bytes, *, require_xz: bool = False) -> list[tuple[str, bytes, bytes, bytes]]:
    if not data.startswith(b"!<arch>\n") or len(data) > MAX_DEB:
        raise DeltaLayoutError("Unsupported Debian ar archive")
    offset, result = 8, []
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[-2:] != b"`\n":
            raise DeltaLayoutError("Invalid Debian ar header")
        try:
            name = header[:16].decode("ascii").strip().rstrip("/")
            size = int(header[48:58].decode("ascii").strip())
        except (ValueError, UnicodeError) as exc:
            raise DeltaLayoutError("Invalid Debian ar member") from exc
        if size < 0 or size > MAX_DEB or offset + 60 + size > len(data):
            raise DeltaLayoutError("Invalid Debian ar size")
        begin = offset + 60
        end = begin + size
        padding = data[end:end + (size % 2)]
        if len(padding) != size % 2:
            raise DeltaLayoutError("Truncated Debian ar padding")
        result.append((name, header, data[begin:end], padding))
        offset = end + size % 2
    names = [member[0] for member in result]
    valid = (
        len(names) == 3 and names[0] == "debian-binary"
        and names[1] in ("control.tar.xz", "control.tar.zst", "control.tar.gz")
        and names[2] in ("data.tar.xz", "data.tar.zst", "data.tar.gz")
    )
    if not valid or (require_xz and names != [
        "debian-binary", "control.tar.xz", "data.tar.xz"
    ]):
        raise DeltaLayoutError(f"Unsupported Debian members: {names!r}")
    return result


def _base_tar(base: Path, kind: str, member_data: bytes, member_name: str) -> bytes:
    """Read an older xz/zstd/gzip installer without adding runtime libraries.

    dpkg-deb is already required to validate and install the .deb; its
    fixed-argument tarfile output is not executed or extracted to disk.
    """
    if member_name.endswith(".xz"):
        raw = lzma.decompress(member_data)
    else:
        option = "--ctrl-tarfile" if kind == "control" else "--fsys-tarfile"
        try:
            result = subprocess.run(
                ["/usr/bin/dpkg-deb", option, str(base)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeltaLayoutError("Cannot decompress previous Debian package") from exc
        if result.returncode:
            raise DeltaLayoutError("Previous Debian package could not be decompressed")
        raw = result.stdout
    if len(raw) > MAX_RAW_TAR:
        raise DeltaLayoutError("Previous Debian tar exceeds limit")
    return raw


def _xz_compress(raw: bytes) -> bytes:
    """Match dpkg-deb's multiblock xz stream, even for large frozen archives.

    Python's lzma.compress emits a single XZ block. dpkg-deb uses the
    multithreaded XZ encoder (even with --threads-max=1), which divides
    large inputs into blocks. A different XZ block layout cannot reproduce
    the official .deb hash. Fixed xz -T2 produces the same byte stream as
    dpkg-deb -Zxz --threads-max=1; the exact target hash is still checked.
    Input/output files avoid duplicating hundreds of MB across pipe buffers.
    """
    if len(raw) > MAX_RAW_TAR:
        raise DeltaLayoutError("Tar exceeds XZ encoding size limit")
    environment = dict(os.environ)
    environment.pop("XZ_OPT", None)
    environment.pop("XZ_DEFAULTS", None)
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as target:
        source.write(raw)
        source.seek(0)
        try:
            result = subprocess.run(
                ["/usr/bin/xz", "-6", "--threads=2", "--stdout"],
                stdin=source, stdout=target, stderr=subprocess.PIPE,
                timeout=600, check=False, env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeltaLayoutError("Cannot reproduce Debian XZ stream") from exc
        if result.returncode:
            raise DeltaLayoutError("XZ encoder could not reproduce Debian stream")
        target.seek(0)
        compressed = target.read(MAX_DEB + 1)
    if len(compressed) > MAX_DEB:
        raise DeltaLayoutError("Compressed tar exceeds Debian size limit")
    return compressed


def _xz_region(data: bytes) -> tuple[int, int]:
    if (len(data) < 44 or not data.startswith(b"\xfd7zXZ\x00")
            or data[-2:] != b"YZ"):
        raise DeltaLayoutError("Requires single-stream xz compressed tar")
    beginning = 12 + (data[12] + 1) * 4
    backward = int.from_bytes(data[-8:-4], "little")
    index = len(data) - 12 - (backward + 1) * 4
    if not 12 < beginning < index < len(data) - 12:
        raise DeltaLayoutError("Invalid xz block/index")
    return beginning, index


def _contents_and_layout(target_xz: bytes):
    """Save only the target xz headers/index; recreate compressed body locally."""
    target_raw = lzma.decompress(target_xz)
    if len(target_raw) > MAX_RAW_TAR:
        raise DeltaLayoutError("Uncompressed tar exceeds safety limit")
    regenerated = _xz_compress(target_raw)
    left, right = _xz_region(target_xz)
    new_left, new_right = _xz_region(regenerated)
    if target_xz[left:right] != regenerated[new_left:new_right]:
        raise DeltaLayoutError("dpkg xz blocks cannot be reproduced exactly")
    return target_raw, {
        "xz_prefix": _b64(target_xz[:left]),
        "xz_suffix": _b64(target_xz[right:]),
        "xz_hash": _hash(target_xz),
        "tar_hash": _hash(target_raw),
        "tar_size": len(target_raw),
    }


def _tar_entries(raw: bytes) -> list[tarfile.TarInfo]:
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            return archive.getmembers()
    except (tarfile.TarError, OSError) as exc:
        raise DeltaLayoutError("Invalid Debian tar layout") from exc


def _member_plan(old_raw: bytes, target_xz: bytes, archive: zipfile.ZipFile, group: int):
    new_raw, meta = _contents_and_layout(target_xz)
    if len(old_raw) > MAX_RAW_TAR:
        raise DeltaLayoutError("Uncompressed base tar exceeds safety limit")
    old_files = {entry.name: entry for entry in _tar_entries(old_raw)}
    cursor, plans = 0, []
    for ordinal, entry in enumerate(_tar_entries(new_raw)):
        if (entry.offset_data < cursor or entry.offset_data + entry.size > len(new_raw)
                or entry.size < 0):
            raise DeltaLayoutError("Invalid target tar offsets")
        leading = new_raw[cursor:entry.offset_data]
        body = new_raw[entry.offset_data:entry.offset_data + entry.size]
        item = {"leading": _b64(leading), "size": entry.size}
        existing = old_files.get(entry.name)
        if (existing is not None and existing.size == entry.size
                and old_raw[existing.offset_data:existing.offset_data + existing.size] == body):
            item.update({"source": "old", "offset": existing.offset_data})
        else:
            # Large files (including frozen app binaries) can change by a few
            # bytes while a ZIP-compressed replacement costs many megabytes.
            # Make a bounded binary patch against the matching previous file.
            # Keep the compressed full body if it is actually cheaper.
            used_bsdiff = False
            if (existing is not None and 4096 <= entry.size <= MAX_BSDIFF_FILE
                    and 0 < existing.size <= MAX_BSDIFF_FILE):
                old_body = old_raw[
                    existing.offset_data:existing.offset_data + existing.size
                ]
                # The *builder* uses the optional native extension, but
                # the shipped bootstrap/reconstruction code needs only Python
                # stdlib. Do not import bsdiff4 at module load time.
                import bsdiff4
                difference = bsdiff4.diff(old_body, body)
                compressed_body_size = len(zlib.compress(body, 6))
                if (len(difference) < compressed_body_size * .90
                        and len(difference) < MAX_PATCH):
                    identifier = f"payload/{group}/{ordinal}.bsdiff"
                    archive.writestr(
                        identifier, difference, compress_type=zipfile.ZIP_STORED
                    )
                    item.update({
                        "source": "bsdiff", "entry": identifier,
                        "old_offset": existing.offset_data,
                        "old_size": existing.size,
                    })
                    used_bsdiff = True
            if not used_bsdiff:
                identifier = f"payload/{group}/{ordinal}"
                archive.writestr(
                    identifier, body, compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                )
                item.update({"source": "zip", "entry": identifier})
        plans.append(item)
        cursor = entry.offset_data + entry.size
    meta["parts"] = plans
    meta["tail"] = _b64(new_raw[cursor:])
    return meta


def build_patch(base: Path, target: Path, patch: Path) -> bool:
    """Create a compact verified patch. False means no affordable delta exists."""
    base_bytes = base.read_bytes()
    target_bytes = target.read_bytes()
    old_members = _ar_members(base_bytes)
    new_members = _ar_members(target_bytes, require_xz=True)
    metadata = {"format": FORMAT, "ar": []}
    try:
        with zipfile.ZipFile(patch, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=False) as output:
            for ordinal, ((old_name, _oh, old_data, _op),
                          (new_name, header, new_data, padding)) in enumerate(
                              zip(old_members, new_members)
                          ):
                if old_name.split(".tar.", 1)[0] != new_name.split(".tar.", 1)[0]:
                    raise DeltaLayoutError("Debian archive member changed")
                entry = {"name": new_name, "header": _b64(header),
                         "padding": _b64(padding)}
                if new_name == "debian-binary":
                    entry["payload"] = {"type": "inline", "data": _b64(new_data)}
                else:
                    entry["payload"] = {
                        "type": "tarxz",
                        **_member_plan(
                            _base_tar(
                                base, new_name.split(".tar.", 1)[0],
                                old_data, old_name,
                            ),
                            new_data, output, ordinal,
                        ),
                    }
                metadata["ar"].append(entry)
            output.writestr("meta.json", json.dumps(
                metadata, separators=(",", ":"), sort_keys=True,
            ), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        if not 0 < patch.stat().st_size <= MAX_PATCH:
            print(
                f"File-aware candidate {patch.stat().st_size} bytes is above "
                f"{MAX_PATCH} byte automatic limit",
                flush=True,
            )
            patch.unlink(missing_ok=True)
            return False
        # Publish no candidate that is not exactly the signed full installer.
        rebuilt = patch.parent / (".verify-" + target.name)
        try:
            apply_patch(base, patch, rebuilt)
            if _hash(rebuilt.read_bytes()) != _hash(target_bytes):
                raise DeltaLayoutError("Delta did not reconstruct exact target Debian")
        finally:
            rebuilt.unlink(missing_ok=True)
        return True
    except BaseException:
        patch.unlink(missing_ok=True)
        raise


def _bsdiff_apply(original: bytes, patch: bytes, expected_size: int) -> bytes:
    """Apply a bounded BSDIFF40 file delta using only Python's standard library.

    Bootstrap upgrades must work on Linux Mint without pip, apt or extra
    downloads. The three bzip2 streams use bsdiff's signed-magnitude 64-bit
    offsets; all output is separately SHA-256 validated by the updater.
    """
    if (len(original) > MAX_BSDIFF_FILE or len(patch) > MAX_PATCH
            or not 0 <= expected_size <= MAX_BSDIFF_FILE
            or len(patch) < 32 or patch[:8] != b"BSDIFF40"):
        raise DeltaLayoutError("Invalid bounded BSDIFF40 patch")

    def signed64(raw: bytes) -> int:
        if len(raw) != 8:
            raise DeltaLayoutError("Truncated BSDIFF40 offset")
        number = raw[7] & 127
        for i in range(6, -1, -1):
            number = number * 256 + raw[i]
        return -number if raw[7] & 128 else number

    control_length = signed64(patch[8:16])
    difference_length = signed64(patch[16:24])
    target_length = signed64(patch[24:32])
    if (control_length < 0 or difference_length < 0
            or target_length != expected_size
            or 32 + control_length + difference_length > len(patch)):
        raise DeltaLayoutError("BSDIFF40 block lengths invalid")
    try:
        control = bz2.decompress(patch[32:32 + control_length])
        difference = bz2.decompress(
            patch[32 + control_length:32 + control_length + difference_length]
        )
        extra = bz2.decompress(patch[32 + control_length + difference_length:])
    except (OSError, EOFError, ValueError) as exc:
        raise DeltaLayoutError("Corrupt BSDIFF40 compressed blocks") from exc
    if (len(control) > MAX_BSDIFF_FILE * 3
            or len(difference) > MAX_BSDIFF_FILE
            or len(extra) > MAX_BSDIFF_FILE):
        raise DeltaLayoutError("Oversized BSDIFF40 block")
    result = bytearray(expected_size)
    new_pos = old_pos = control_pos = diff_pos = extra_pos = 0
    while new_pos < expected_size:
        if control_pos + 24 > len(control):
            raise DeltaLayoutError("Truncated BSDIFF40 control block")
        x = signed64(control[control_pos:control_pos + 8])
        y = signed64(control[control_pos + 8:control_pos + 16])
        z = signed64(control[control_pos + 16:control_pos + 24])
        control_pos += 24
        # BSDIFF40 permits a cursor-only control (x=y=0, z!=0): this
        # legitimately repositions the old-file offset before writing.
        # Only a completely stationary instruction is invalid.
        if (x < 0 or y < 0 or (x + y == 0 and z == 0)
                or x + y > expected_size - new_pos
                or x > len(difference) - diff_pos
                or y > len(extra) - extra_pos):
            raise DeltaLayoutError("Invalid BSDIFF40 control instruction")
        for index in range(x):
            src = old_pos + index
            value = original[src] if 0 <= src < len(original) else 0
            result[new_pos + index] = (
                difference[diff_pos + index] + value
            ) & 0xFF
        new_pos += x
        old_pos += x
        diff_pos += x
        result[new_pos:new_pos + y] = extra[extra_pos:extra_pos + y]
        new_pos += y
        extra_pos += y
        old_pos += z
    return bytes(result)


def _rebuild_tar(old: bytes, plan: dict, archive: zipfile.ZipFile) -> bytes:
    if len(old) > MAX_RAW_TAR:
        raise DeltaLayoutError("Base tar too large")
    output = bytearray()
    for item in plan["parts"]:
        leading = _decode(item["leading"])
        size = item["size"]
        if not isinstance(size, int) or not 0 <= size <= MAX_RAW_TAR:
            raise DeltaLayoutError("Invalid tar entry size")
        output.extend(leading)
        if item["source"] == "old":
            offset = item["offset"]
            if not isinstance(offset, int) or not 0 <= offset <= len(old) - size:
                raise DeltaLayoutError("Invalid base tar reference")
            output.extend(old[offset:offset + size])
        elif item["source"] == "zip":
            entry = item["entry"]
            if (not isinstance(entry, str) or not entry.startswith("payload/")
                    or entry not in archive.namelist()):
                raise DeltaLayoutError("Invalid delta payload reference")
            if archive.getinfo(entry).file_size != size:
                raise DeltaLayoutError("Wrong delta payload size")
            output.extend(archive.read(entry))
        elif item["source"] == "bsdiff":
            entry = item["entry"]
            offset, old_size = item["old_offset"], item["old_size"]
            if (not isinstance(entry, str)
                    or not entry.startswith("payload/")
                    or entry not in archive.namelist()
                    or not isinstance(offset, int) or not isinstance(old_size, int)
                    or old_size <= 0 or old_size > MAX_BSDIFF_FILE
                    or offset < 0 or offset > len(old) - old_size
                    or archive.getinfo(entry).file_size > MAX_PATCH):
                raise DeltaLayoutError("Invalid delta binary patch reference")
            new_body = _bsdiff_apply(
                old[offset:offset + old_size], archive.read(entry), size
            )
            if len(new_body) != size:
                raise DeltaLayoutError("Wrong binary patch output size")
            output.extend(new_body)
        else:
            raise DeltaLayoutError("Invalid delta source")
        if len(output) > MAX_RAW_TAR:
            raise DeltaLayoutError("Rebuilt tar exceeds limit")
    output.extend(_decode(plan["tail"]))
    if (len(output) != plan["tar_size"]
            or _hash(output) != plan["tar_hash"]):
        raise DeltaLayoutError("Rebuilt tar checksum mismatch")
    return bytes(output)


def _rebuild_xz(raw: bytes, plan: dict) -> bytes:
    compressed = _xz_compress(raw)
    start, end = _xz_region(compressed)
    rebuilt = (_decode(plan["xz_prefix"]) + compressed[start:end]
               + _decode(plan["xz_suffix"]))
    if _hash(rebuilt) != plan["xz_hash"]:
        raise DeltaLayoutError("Reconstructed compressed tar checksum mismatch")
    return rebuilt


def apply_patch(base: Path, patch: Path, output: Path) -> None:
    """Apply a verified patch without unpacking files or invoking any commands."""
    old_members = _ar_members(base.read_bytes())
    old = {name.split(".tar.", 1)[0]: (
        name, data
    ) for name, _h, data, _p in old_members}
    with zipfile.ZipFile(patch) as source:
        meta_info = source.getinfo("meta.json")
        if meta_info.file_size > MAX_META:
            raise DeltaLayoutError("Delta manifest too large")
        meta = json.loads(source.read("meta.json"))
        if meta.get("format") != FORMAT or len(meta.get("ar", [])) != 3:
            raise DeltaLayoutError("Unsupported content-delta format")
        result = bytearray(b"!<arch>\n")
        for item in meta["ar"]:
            name = item["name"]
            key = name.split(".tar.", 1)[0]
            if key not in old:
                raise DeltaLayoutError("Unexpected Debian member")
            header, padding = _decode(item["header"]), _decode(item["padding"])
            if len(header) != 60 or header[-2:] != b"`\n":
                raise DeltaLayoutError("Invalid patched ar header")
            plan = item["payload"]
            if plan["type"] == "inline" and name == "debian-binary":
                payload = _decode(plan["data"])
            elif plan["type"] == "tarxz" and name.endswith(".tar.xz"):
                old_name, old_data = old[key]
                payload = _rebuild_xz(
                    _rebuild_tar(
                        _base_tar(base, key, old_data, old_name), plan, source
                    ),
                    plan,
                )
            else:
                raise DeltaLayoutError("Unsupported patched ar payload")
            if int(header[48:58].decode("ascii").strip()) != len(payload):
                raise DeltaLayoutError("Patched ar member size mismatch")
            if len(padding) != len(payload) % 2:
                raise DeltaLayoutError("Incorrect patched ar padding")
            result.extend(header)
            result.extend(payload)
            result.extend(padding)
            if len(result) > MAX_DEB:
                raise DeltaLayoutError("Reconstructed Debian exceeds size limit")
        if [a[0] for a in _ar_members(bytes(result), require_xz=True)] != [
                "debian-binary", "control.tar.xz", "data.tar.xz"]:
            raise DeltaLayoutError("Invalid reconstructed Debian member sequence")
    output.write_bytes(result)
