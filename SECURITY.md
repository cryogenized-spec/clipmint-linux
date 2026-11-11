# ClipMint preview security and release trust

## Current trust limitation

ClipMint is an experimental desktop application that can handle clipboard data and propose system-level `.deb` installers. **Its current GitHub release `SHA256SUMS` file is served from the same account as the installer and is NOT an independently authenticated signature.** A malicious release uploaded using compromised publisher credentials could replace both. CI green status alone does not remove that threat.

**No automatic package staging in the v0.6.0 manual-update beta.** ClipMint does not perform privileged installation; Linux Mint package-manager approval remains separate. An older saved automatic-update opt-in now allows **availability checks only**, never downloads. Manual Download shows the full-installer size and requires explicit approval, even when a smaller patch may be used. The patch size ceiling remains 20 MiB when that future authenticated automation is permitted; it does not authorize staging today.

## Planned signing protocol (not yet activated)

The repository's next security milestone should introduce an owner-controlled **Ed25519** signing identity kept **outside ordinary GitHub Actions release-token access**, with the corresponding public key pinned in a reviewed application release and documented fingerprint.

The release manifest must bind the exact tag, build commit, version, package size and SHA-256, and the hashes and sizes of every patch and optional bootstrap asset. Verify the manifest signature **before** permitting a new background download. Distinguish unknown keys, key rotation, revocation, expired metadata, missing signatures and rollback attempts. Reject rather than falling back to an untrusted release.

A second account or offline signing process will need to hold the private key. **No signing key has been generated, stored, or enabled by this documentation.** Do not place a private key in the source tree, release assets, public CI logs or an ordinary workflow secret accessible to untrusted pull requests.

Until the signing and verification deployment is complete, version/checksum checks support **integrity verification**, not standalone release authenticity.

## Data and privacy

Clipboard history is plaintext by default and may contain sensitive content; application filtering is best-effort. Keyring encryption is opt-in and has recovery/backup constraints. A deliberately retained plaintext migration copy can be removed from Settings after verification; file deletion is not a guarantee of forensic erasure of remnants or backups.

The experimental password/variable vault has **not** had an independent security audit. Clipboard copies on X11 can be observed by other local processes. Do not assume the vault is equivalent to a dedicated password manager.

## Reporting a vulnerability

If the GitHub repository offers **private vulnerability reporting** in its Security tab, use that confidential route instead of opening a public issue containing exploit details, credentials or private history. Otherwise, contact the repository maintainer through an established private channel. Avoid attaching secrets or production clipboard databases to public reports.

## Engineering requirements

Pin external CI actions to reviewed immutable commit hashes; issue read-only workflow tokens except in isolated publishing steps; use least privilege for release uploads; verify release artifacts and Debian package identity; enforce file and download size caps; preserve fail-closed security checks and dedicated regression tests.
