"""Optional encrypted history store using libsodium and the desktop Secret Service.

No clipboard content or searchable preview is written to plaintext fields in
secure-history.sqlite3. The legacy SQLite file is never modified automatically.
This is authenticated encryption at the application layer, NOT SQLCipher:
metadata (kind/bin/timestamps/count) remains visible on disk.
"""
from __future__ import annotations
import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import shutil

from nacl.secret import SecretBox
from nacl.exceptions import CryptoError

from .store import ClipStore, Clip
from .clipboard_formats import bundle_to_bytes, bundle_from_bytes, sensitive_payload

KEY_SERVICE = "clipmint.secure-history.v1"
KEY_NAME = "local-history-key"


class HistorySecurityError(RuntimeError):
    pass


def secure_path() -> Path:
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return root / "clipmint" / "secure-history.sqlite3"


def key_from_secret_service(create=False) -> bytes:
    """Never accept backends that silently store passwords in plaintext files."""
    try:
        from keyring.backends.SecretService import Keyring as SecretServiceKeyring
    except ImportError as exc:
        raise HistorySecurityError("Secret Service keyring is not installed") from exc
    try:
        backend = SecretServiceKeyring()
        if backend.priority <= 0:
            raise HistorySecurityError("Desktop Secret Service keyring is unavailable")
        encoded = backend.get_password(KEY_SERVICE, KEY_NAME)
        if encoded is None and create:
            if secure_path().exists():
                raise HistorySecurityError("Existing encrypted history key is unavailable")
            encoded = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
            backend.set_password(KEY_SERVICE, KEY_NAME, encoded)
        if not encoded:
            raise HistorySecurityError("Secure history key is missing or keyring is locked")
        result = base64.b64decode(encoded, validate=True)
        if len(result) != SecretBox.KEY_SIZE:
            raise HistorySecurityError("Keyring value has the wrong key length")
        return result
    except HistorySecurityError:
        raise
    except Exception as exc:
        raise HistorySecurityError("Could not access the unlocked desktop keyring") from exc


class EncryptedClipStore(ClipStore):
    def __init__(self, path: Path, key: bytes, max_unpinned=250):
        if len(key) != SecretBox.KEY_SIZE:
            raise ValueError("Invalid history encryption key")
        self.box = SecretBox(key)
        super().__init__(path, max_unpinned=max_unpinned, index_plaintext=False)
        os.chmod(self.path, 0o600)

    def _seal(self, data: bytes, preview: str, formats: dict[str, bytes] | None) -> bytes:
        value = {
            "payload": base64.b64encode(data).decode("ascii"),
            "preview": preview,
            "formats": base64.b64encode(bundle_to_bytes(formats or {})).decode("ascii"),
        }
        return bytes(self.box.encrypt(json.dumps(value).encode("utf-8")))

    def _open(self, sealed: bytes) -> tuple[bytes, str, dict[str, bytes]]:
        try:
            record = json.loads(self.box.decrypt(sealed))
            return (
                base64.b64decode(record["payload"], validate=True),
                record["preview"],
                bundle_from_bytes(base64.b64decode(record["formats"], validate=True)),
            )
        except (CryptoError, KeyError, ValueError, TypeError) as exc:
            raise HistorySecurityError("Encrypted history entry failed authentication") from exc

    def _encode_template(self, text: str) -> bytes:
        # Secure history never writes reusable template bodies into plaintext
        # SQLite columns, FTS indexes, or the old unencrypted database.
        return bytes(self.box.encrypt(text.encode("utf-8")))

    def _decode_template(self, value: bytes) -> str:
        try:
            return self.box.decrypt(value).decode("utf-8")
        except (CryptoError, UnicodeError) as exc:
            raise HistorySecurityError("Encrypted template failed authentication") from exc

    def _history_payload_is_sealed(self) -> bool:
        return True

    def add(self, kind: str, content: bytes, preview: str, bin_name="Work",
            formats: dict[str, bytes] | None = None):
        # Sensitive items are excluded entirely, even from encrypted history.
        # Otherwise caller-supplied text could be persisted inadvertently.
        if sensitive_payload(kind, content, formats):
            return None
        # Dedup based on unencrypted content held *only* in process memory.
        row = self.conn.execute(
            "SELECT id,content FROM clips WHERE bin=? ORDER BY id DESC LIMIT 1",
            (bin_name,),
        ).fetchone()
        if row:
            old_content, _, old_formats = self._open(bytes(row[1]))
            if old_content == content and old_formats == (formats or {}):
                self.conn.execute(
                    "UPDATE clips SET created_at="
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                    (row[0],),
                )
                self.conn.commit()
                return row[0]
        return super().add(kind, self._seal(content, preview, formats),
                           "🔒 Encrypted history item", bin_name)

    def get(self, clip_id: int):
        result = super().get(clip_id)
        if result is None: return None
        kind, cipher = result
        data, _, _ = self._open(cipher)
        return kind, data

    def get_formats(self, clip_id: int):
        result = super().get(clip_id)
        return self._open(result[1])[2] if result else {}

    def search(self, query="", bin_name="Work", sort="Latest first",
               category="All", tag="", favorites_only=False):
        # Decrypt matching previews strictly in-process. No plaintext FTS
        # index is ever constructed for encrypted history.
        from .store import classify
        rows = self.conn.execute(
            """SELECT id,kind,content,pinned,created_at,bin,favorite FROM clips
               WHERE bin=? ORDER BY id DESC LIMIT 1000""", (bin_name,)
        )
        clips = []
        for ident, kind, raw, pinned, date, bucket, favorite in rows:
            _, preview, _ = self._open(bytes(raw))
            if query.casefold() not in preview.casefold():
                continue
            if favorites_only and not favorite:
                continue
            if tag and tag.lower().strip() not in self.tags(ident):
                continue
            clip = Clip(ident, kind, preview, bool(pinned), date, bucket, bool(favorite))
            if category != "All" and classify(clip) != category:
                continue
            clips.append(clip)
        if sort in ("A–Z", "Z–A"):
            clips.sort(key=lambda c: (c.preview.casefold(), c.id),
                       reverse=(sort == "Z–A"))
        elif sort == "Oldest first":
            clips.sort(key=lambda c: c.id)
        return clips

    @classmethod
    def migrate_legacy(cls, legacy: ClipStore, target: Path, key: bytes):
        """Create a new encrypted DB separately; leave the original untouched.

        If any row fails, the staging file is discarded and the previous
        database remains as it was. The user must handle legacy cleanup.
        """
        target = Path(target)
        if target.exists():
            raise HistorySecurityError("Encrypted history already exists")
        stage = target.with_name("." + target.name + ".staging")
        if stage.exists():
            raise HistorySecurityError("A previous migration staging file exists")
        old_umask = os.umask(0o077)
        secure = None
        try:
            secure = cls(stage, key, legacy.max_unpinned)
            for bin_name in legacy.bins():
                if bin_name not in secure.bins():
                    secure.add_bin(bin_name)
            for ident, kind, content, formats, preview, pinned, date, bucket, favorite in \
                    legacy.conn.execute(
                        "SELECT id,kind,content,formats,preview,pinned,created_at,bin,favorite "
                        "FROM clips ORDER BY id"
                    ):
                sealed = secure._seal(bytes(content), preview,
                        bundle_from_bytes(bytes(formats) if formats else None))
                secure.conn.execute(
                    """INSERT INTO clips
                       (id,kind,content,formats,preview,pinned,created_at,bin,favorite)
                       VALUES(?,?,?,NULL,?,?,?,?,?)""",
                    (ident, kind, sealed, "🔒 Encrypted history item", pinned, date, bucket, favorite),
                )
            # Copy organisational metadata and re-seal template bodies. Names
            # remain visible, while template text is encrypted in the target.
            secure.conn.executemany(
                "INSERT INTO clip_tags(clip_id,tag) VALUES(?,?)",
                legacy.conn.execute("SELECT clip_id,tag FROM clip_tags").fetchall()
            )
            for _, name, body in legacy.templates():
                secure.save_template(name, body)
            secure.conn.commit()
            secure.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            secure.close()
            secure = None
            os.replace(stage, target)
            return cls(target, key, legacy.max_unpinned)
        except Exception:
            if secure is not None:
                secure.close()
            for suffix in ("", "-wal", "-shm"):
                stage.with_name(stage.name + suffix).unlink(missing_ok=True)
            raise
        finally:
            os.umask(old_umask)
