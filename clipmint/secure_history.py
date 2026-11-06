"""Optional encrypted history store using libsodium and the desktop Secret Service.

No clipboard content or searchable preview is written to plaintext fields in
secure-history.sqlite3. The legacy SQLite file is never modified automatically.
This is authenticated encryption at the application layer, NOT SQLCipher:
metadata (kind/bin/timestamps/count) remains visible on disk.
"""
from __future__ import annotations
import base64
from dataclasses import replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
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
        self._dedup_key = key
        self.corrupt_row_ids: set[int] = set()
        super().__init__(path, max_unpinned=max_unpinned, index_plaintext=False)
        os.chmod(self.path, 0o600)
        # Persist non-destructive quarantine across restarts. Do not rely
        # only on a volatile warning or assume a keyed marker is recognisable.
        columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(clips)")
        }
        if "corrupt" not in columns:
            self.conn.execute(
                "ALTER TABLE clips ADD COLUMN corrupt INTEGER NOT NULL DEFAULT 0"
            )
            self.conn.commit()
        self.corrupt_row_ids = {
            ident for (ident,) in self.conn.execute(
                "SELECT id FROM clips WHERE corrupt=1"
            )
        }
        # One-time upgrade on key unlock, not during each clipboard capture.
        # Rows without a fingerprint predate this version.
        self._backfill_legacy_fingerprints()

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

    def _encrypted_fingerprint(
        self, kind: str, content: bytes, formats: dict[str, bytes] | None,
    ) -> bytes:
        """Secret-keyed HMAC; unlike plain SHA256 it resists guessable text."""
        packed = bundle_to_bytes(dict(sorted((formats or {}).items())))
        message = (b"clipmint-dedup-v1\\0" + kind.encode("ascii") +
                   len(content).to_bytes(8, "big") + content + packed)
        return hmac.digest(self._dedup_key, message, hashlib.sha256)

    def _backfill_legacy_fingerprints(self) -> None:
        """Backfill old encrypted rows in bounded transactions, once per DB.

        A crash can interrupt a batch safely; the next open resumes with
        remaining NULL rows. No plaintext enters SQLite/FTS.
        """
        while True:
            identifiers = [ident for (ident,) in self.conn.execute(
                "SELECT id FROM clips WHERE fingerprint IS NULL LIMIT 32"
            )]
            if not identifiers:
                break
            with self.conn:
                for ident in identifiers:
                    row = self.conn.execute(
                        "SELECT kind,content FROM clips WHERE id=?", (ident,)
                    ).fetchone()
                    if row is None:
                        continue
                    kind, sealed = row
                    try:
                        content, _preview, formats = self._open(bytes(sealed))
                    except HistorySecurityError:
                        # Keep the ciphertext for possible recovery without
                        # letting a damaged record block healthy history.
                        # The marker is keyed and intentionally cannot match
                        # a valid plaintext content fingerprint.
                        self.corrupt_row_ids.add(ident)
                        fingerprint = hmac.digest(
                            self._dedup_key,
                            b"clipmint-corrupt-v1\\0" +
                            int(ident).to_bytes(8, "big") + bytes(sealed),
                            hashlib.sha256,
                        )
                    else:
                        fingerprint = self._encrypted_fingerprint(
                            kind, content, formats
                        )
                    self.conn.execute(
                        "UPDATE clips SET fingerprint=?, corrupt=? WHERE id=?",
                        (sqlite3.Binary(fingerprint),
                         int(ident in self.corrupt_row_ids), ident)
                    )

    def _find_encrypted_duplicate(
        self, kind: str, content: bytes, formats: dict[str, bytes] | None,
        bin_name: str, fingerprint: bytes,
    ) -> int | None:
        expected = formats or {}
        # Efficient keyed lookup for new rows, with a lazy fallback for old
        # encrypted databases which do not yet have fingerprint metadata.
        # A current database has all fingerprints populated, so this indexed
        # lookup decrypts at most matching candidates, never every old row.
        rows = self.conn.execute(
            """SELECT id,content FROM clips
               WHERE bin=? AND kind=? AND fingerprint=?
               ORDER BY touch_seq DESC""",
            (bin_name, kind, sqlite3.Binary(fingerprint))
        )
        for ident, sealed in rows:
            prior_bytes, _preview, prior_formats = self._open(bytes(sealed))
            if prior_bytes == content and prior_formats == expected:
                return ident
        return None

    def _history_payload_is_sealed(self) -> bool:
        """The encrypted store checks secrets before sealing its payload."""
        return True

    def add(self, kind: str, content: bytes, preview: str, bin_name="Work",
            formats: dict[str, bytes] | None = None):
        if kind not in ("text", "image", "files"):
            raise ValueError("Unsupported clipboard type")
        if not content:
            return None
        if bin_name not in self.bins():
            raise ValueError("Unknown accumulation bin")
        # Do not persist even encrypted sensitive clipboard entries.
        if sensitive_payload(kind, content, formats):
            return None
        fingerprint = self._encrypted_fingerprint(kind, content, formats)
        found = self._find_encrypted_duplicate(
            kind, content, formats, bin_name, fingerprint
        )
        if found is not None:
            return self._touch_duplicate(found, fingerprint)
        return super().add(
            kind, self._seal(content, preview, formats),
            "🔒 Encrypted history item", bin_name,
            _sealed_fingerprint=fingerprint
        )

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
        condition = "corrupt=0" if bin_name is None else "bin=? AND corrupt=0"
        params = () if bin_name is None else (bin_name,)
        rows = self.conn.execute(
            """SELECT id,kind,content,pinned,created_at,bin,favorite,touch_seq
               FROM clips WHERE """ + condition +
            """ ORDER BY touch_seq DESC,id DESC LIMIT 1000""", params
        )
        items: list[tuple[int, Clip]] = []
        newly_damaged: list[int] = []
        for ident, kind, raw, pinned, date, bucket, favorite, sequence in rows:
            try:
                _, preview, _ = self._open(bytes(raw))
            except HistorySecurityError:
                # Preserve the unreadable encrypted row for manual recovery,
                # but do not let it hide unrelated healthy clipboard history.
                self.corrupt_row_ids.add(ident)
                newly_damaged.append(ident)
                continue
            if query.casefold() not in preview.casefold():
                continue
            if favorites_only and not favorite:
                continue
            if tag and tag.lower().strip() not in self.tags(ident):
                continue
            clip = Clip(ident, kind, preview, bool(pinned), date, bucket, bool(favorite))
            if category != "All" and classify(clip) != category:
                continue
            items.append((sequence, clip))
        if newly_damaged:
            with self.conn:
                self.conn.executemany(
                    "UPDATE clips SET corrupt=1 WHERE id=?",
                    [(ident,) for ident in newly_damaged],
                )
        if sort in ("A–Z", "Z–A"):
            items.sort(key=lambda row: (row[1].preview.casefold(), row[1].id),
                       reverse=(sort == "Z–A"))
        elif sort == "Oldest first":
            items.sort(key=lambda row: (row[0], row[1].id))
        elif sort == "Best match" and query.strip():
            # Rank only in process memory while unlocked. Never build a
            # plaintext FTS index or write query scores into SQLite.
            needle = query.strip().casefold()
            def relevance(row):
                sequence, clip = row
                text = clip.preview.casefold()
                return (
                    0 if text == needle else 1 if text.startswith(needle) else 2,
                    text.find(needle),
                    -sequence,
                )
            items.sort(key=relevance)
        return [clip for _sequence, clip in items]

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
            for ident, kind, content, formats, preview, pinned, date, bucket, favorite, touched in \
                    legacy.conn.execute(
                        "SELECT id,kind,content,formats,preview,pinned,created_at,"
                        "bin,favorite,touch_seq FROM clips ORDER BY id"
                    ):
                sealed = secure._seal(bytes(content), preview,
                        bundle_from_bytes(bytes(formats) if formats else None))
                raw_formats = bundle_from_bytes(
                    bytes(formats) if formats else None
                )
                fingerprint = secure._encrypted_fingerprint(
                    kind, bytes(content), raw_formats
                )
                secure.conn.execute(
                    """INSERT INTO clips
                       (id,kind,content,formats,preview,pinned,created_at,bin,
                        favorite,touch_seq,fingerprint)
                       VALUES(?,?,?,NULL,?,?,?,?,?,?,?)""",
                    (ident, kind, sealed, "🔒 Encrypted history item",
                     pinned, date, bucket, favorite, touched,
                     sqlite3.Binary(fingerprint)),
                )
            # Copy organisational metadata and re-seal template bodies. Names
            # remain visible, while template text is encrypted in the target.
            secure.conn.executemany(
                "INSERT INTO clip_tags(clip_id,tag) VALUES(?,?)",
                legacy.conn.execute("SELECT clip_id,tag FROM clip_tags").fetchall()
            )
            for _, name, body in legacy.templates():
                secure.save_template(name, body)
            secure.conn.execute("UPDATE clips SET touch_seq=id WHERE touch_seq=0")
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
