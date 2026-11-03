"""Locally encrypted, opt-in Secrets & Variables vault.

No raw clipboard data is imported. The entire entries document, including
labels, is authenticated-encrypted using libsodium SecretBox (XSalsa20-Poly1305).
Argon2id derives its key from a user passphrase; no key is persisted.
X11 still exposes a secret to other local processes while it is copied.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import secrets
import tempfile

from nacl import exceptions as nacl_exceptions
from nacl import pwhash, secret, utils

VERSION = 1
OPSLIMIT = pwhash.argon2id.OPSLIMIT_INTERACTIVE
MEMLIMIT = pwhash.argon2id.MEMLIMIT_INTERACTIVE
MAX_VAULT_BYTES = 16 * 1024 * 1024


class VaultError(Exception):
    """A user-facing vault operation failed; do not include secret values."""


def default_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return base / "clipmint" / "secrets.vault"


def _encode(binary: bytes) -> str:
    return base64.b64encode(binary).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _derive(passphrase: str, salt: bytes, operations: int, memory: int) -> bytes:
    if not isinstance(passphrase, str):
        raise VaultError("Passphrase must be text")
    return pwhash.argon2id.kdf(
        secret.SecretBox.KEY_SIZE, passphrase.encode("utf-8"), salt,
        opslimit=operations, memlimit=memory
    )


def _atomic_private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise VaultError("Refusing a symbolic-link vault path")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".clipmint-vault-", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        os.chmod(path, 0o600)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Vault:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_path()
        self._key: bytes | None = None
        self._entries: list[dict] = []
        self._metadata: dict = {}

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    @property
    def configured(self) -> bool:
        return self.path.exists()

    def lock(self) -> None:
        # Python cannot guarantee secure erasure of copies held in process RAM.
        self._entries = []
        self._key = None
        self._metadata = {}

    def _read(self) -> dict:
        if self.path.is_symlink():
            raise VaultError("Refusing a symbolic-link vault path")
        try:
            if self.path.stat().st_size > MAX_VAULT_BYTES:
                raise VaultError("Vault file is unexpectedly large")
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("version") != VERSION:
                raise VaultError("Unsupported vault version")
            ops = value.get("opslimit")
            mem = value.get("memlimit")
            if (type(ops) is not int or not 2 <= ops <= 6 or
                    type(mem) is not int or not 16*1024*1024 <= mem <= 512*1024*1024):
                raise VaultError("Invalid key-derivation parameters")
            if len(_decode(value["salt"])) != pwhash.argon2id.SALTBYTES:
                raise VaultError("Invalid vault salt")
            if not isinstance(value["ciphertext"], str):
                raise VaultError("Invalid vault ciphertext")
            return value
        except (OSError, KeyError, ValueError, TypeError, binascii.Error) as exc:
            raise VaultError("Vault file is unreadable or corrupted") from exc

    def _encrypt_document(self, key: bytes, metadata: dict, entries: list[dict]) -> bytes:
        plaintext = json.dumps(
            {"entries": entries}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        ciphertext = secret.SecretBox(key).encrypt(
            plaintext, nonce=utils.random(secret.SecretBox.NONCE_SIZE)
        )
        doc = {**metadata, "version": VERSION, "ciphertext": _encode(ciphertext)}
        return json.dumps(doc, separators=(",", ":")).encode("ascii")

    def create(self, passphrase: str) -> None:
        if self.configured:
            raise VaultError("A vault already exists; unlock it instead")
        if len(passphrase) < 12:
            raise VaultError("Use a passphrase of at least 12 characters")
        salt = utils.random(pwhash.argon2id.SALTBYTES)
        key = _derive(passphrase, salt, OPSLIMIT, MEMLIMIT)
        metadata = {
            "version": VERSION, "salt": _encode(salt),
            "opslimit": int(OPSLIMIT), "memlimit": int(MEMLIMIT),
        }
        _atomic_private_write(
            self.path, self._encrypt_document(key, metadata, [])
        )
        self._key, self._metadata, self._entries = key, metadata, []

    def unlock(self, passphrase: str) -> None:
        self.lock()
        doc = self._read()
        try:
            key = _derive(
                passphrase, _decode(doc["salt"]), doc["opslimit"], doc["memlimit"]
            )
            decrypted = secret.SecretBox(key).decrypt(_decode(doc["ciphertext"]))
            payload = json.loads(decrypted.decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
                raise ValueError("Invalid entries payload")
            entries = payload["entries"]
            if any(
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("value"), str)
                or item.get("kind") not in ("Secret", "Variable")
                for item in entries
            ):
                raise ValueError("Invalid entries data")
        except (nacl_exceptions.CryptoError, ValueError, TypeError, KeyError) as exc:
            raise VaultError("Incorrect passphrase or damaged vault") from exc
        self._key = key
        self._metadata = {k: v for k, v in doc.items() if k != "ciphertext"}
        self._entries = entries

    def _require_unlocked(self) -> None:
        if self._key is None:
            raise VaultError("Unlock the vault first")

    def _save(self) -> None:
        self._require_unlocked()
        data = self._encrypt_document(self._key, self._metadata, self._entries)
        if len(data) > MAX_VAULT_BYTES:
            raise VaultError("Vault reached its size limit")
        _atomic_private_write(self.path, data)

    def list_entries(self) -> list[dict]:
        self._require_unlocked()
        return [
            {"id": e["id"], "name": e["name"], "kind": e["kind"]}
            for e in self._entries
        ]

    def get_value(self, entry_id: str) -> str:
        self._require_unlocked()
        for entry in self._entries:
            if entry["id"] == entry_id:
                return entry["value"]
        raise VaultError("Entry not found")

    def add(self, name: str, value: str, kind: str) -> str:
        self._require_unlocked()
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise VaultError("Provide a name of at most 120 characters")
        if not isinstance(value, str) or not value or len(value) > 65536:
            raise VaultError("Value cannot be blank or longer than 65,536 characters")
        if kind not in ("Secret", "Variable"):
            raise VaultError("Choose Secret or Variable")
        entry_id = secrets.token_hex(12)
        self._entries.append({
            "id": entry_id, "name": name.strip(), "value": value, "kind": kind
        })
        try:
            self._save()
        except Exception:
            self._entries.pop()
            raise
        return entry_id

    def remove(self, entry_id: str) -> None:
        self._require_unlocked()
        existing = self._entries
        self._entries = [e for e in existing if e["id"] != entry_id]
        if len(self._entries) == len(existing):
            raise VaultError("Entry not found")
        try:
            self._save()
        except Exception:
            self._entries = existing
            raise

    def change_passphrase(self, current: str, replacement: str) -> None:
        self._require_unlocked()
        if len(replacement) < 12:
            raise VaultError("Use a passphrase of at least 12 characters")
        doc = self._read()
        try:
            candidate = _derive(
                current, _decode(doc["salt"]), doc["opslimit"], doc["memlimit"]
            )
            secret.SecretBox(candidate).decrypt(_decode(doc["ciphertext"]))
        except (nacl_exceptions.CryptoError, ValueError, TypeError) as exc:
            raise VaultError("Current passphrase is incorrect") from exc
        salt = utils.random(pwhash.argon2id.SALTBYTES)
        metadata = {
            "version": VERSION, "salt": _encode(salt),
            "opslimit": int(OPSLIMIT), "memlimit": int(MEMLIMIT),
        }
        new_key = _derive(replacement, salt, OPSLIMIT, MEMLIMIT)
        _atomic_private_write(
            self.path, self._encrypt_document(new_key, metadata, self._entries)
        )
        self._key, self._metadata = new_key, metadata

    def encrypted_backup(self, target: Path) -> None:
        self._read()  # Check format and refuse symlinks before copying.
        target = Path(target)
        if target.resolve() == self.path.resolve():
            raise VaultError("Backup must use a different file")
        _atomic_private_write(target, self.path.read_bytes())

    def restore_backup(self, source: Path) -> None:
        """Restore only when no vault exists; old passphrase is still required."""
        if self.configured:
            raise VaultError("Delete or back up the existing vault before restoring")
        candidate = Vault(Path(source))
        candidate._read()  # Validate envelope before copying ciphertext.
        _atomic_private_write(self.path, candidate.path.read_bytes())
        self.lock()

    def wipe(self) -> None:
        self.lock()
        if self.path.is_symlink():
            raise VaultError("Refusing a symbolic-link vault path")
        self.path.unlink(missing_ok=True)
