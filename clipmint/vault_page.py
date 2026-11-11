"""Construct vault controls without owning encryption or credentials."""
from __future__ import annotations
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

def build_vault_page(w):
    page = QWidget()
    layout = QVBoxLayout(page)
    heading = QLabel("Secrets & Variables · encrypted local vault")
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    warning = QLabel(
        "Vault entries, including names, are encrypted on disk with "
        "libsodium SecretBox and an Argon2id-derived key. Ordinary "
        "clipboard history is NOT encrypted. X11 makes copied values "
        "visible to other local applications until the clipboard clears."
    )
    warning.setWordWrap(True)
    layout.addWidget(warning)
    w.vault_status = QLabel("")
    layout.addWidget(w.vault_status)
    w.vault_items = QListWidget()
    w.vault_items.itemDoubleClicked.connect(
        lambda _item: w.reveal_vault_value()
    )
    layout.addWidget(w.vault_items, 1)
    auth = QHBoxLayout()
    w.vault_actions = {}
    for name, label, callback in (
        ("create", "Create vault", w.create_vault),
        ("unlock", "Unlock", w.unlock_vault),
        ("lock", "Lock", w.lock_vault),
        ("backup", "Encrypted backup", w.backup_vault),
        ("restore", "Restore backup", w.restore_vault),
    ):
        btn = QPushButton(label)
        btn.clicked.connect(callback)
        auth.addWidget(btn)
        w.vault_actions[name] = btn
    layout.addLayout(auth)
    commands = QHBoxLayout()
    for name, label, callback in (
        ("add", "New entry", w.add_vault_entry),
        ("reveal", "Reveal", w.reveal_vault_value),
        ("copy", "Copy", w.copy_vault_value),
        ("remove", "Delete entry", w.remove_vault_entry),
    ):
        btn = QPushButton(label)
        btn.clicked.connect(callback)
        commands.addWidget(btn)
        w.vault_actions[name] = btn
    layout.addLayout(commands)
    maintenance = QHBoxLayout()
    for name, label, callback in (
        ("rotate", "Change passphrase", w.change_vault_passphrase),
        ("wipe", "Delete vault", w.wipe_vault),
    ):
        btn = QPushButton(label)
        btn.clicked.connect(callback)
        maintenance.addWidget(btn)
        w.vault_actions[name] = btn
    layout.addLayout(maintenance)
    note = QLabel(
        "There is no password reset: retain your passphrase and an "
        "encrypted backup. The vault locks automatically after five "
        "minutes without a vault action. It also locks when ClipMint closes."
    )
    note.setWordWrap(True)
    layout.addWidget(note)
    w.pages.addWidget(page)
    w.refresh_vault()
