# ClipMint — clipboard, screenshots and recordings for Linux Mint

ClipMint is a **preview** desktop application for **Linux Mint 22, Cinnamon/X11, x86-64**. It provides clipboard history, searchable collections, region screenshots, and MP4/GIF screen recording. It is a native Linux application; no Wine is required.

**Latest builds:** [GitHub Releases](https://github.com/cryogenized-spec/clipmint-linux/releases) · **Current work:** [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Security](SECURITY.md)

## Features and platform limits

- Clipboard history for text and supported images, with Work, Personal, Temporary and user-created collections, search, pinning, sorting and history controls.
- Configurable Cinnamon global shortcuts for screenshots, screen recording and clipboard popup. The watcher can remain active when the main window is hidden. **Quit** actually stops it.
- Region screenshot selection, screenshot library, and MP4/GIF region recording with confirmation before keeping completed recordings.
- Optional OCR using system Tesseract packages. Optional encrypted clipboard history using the Linux desktop Secret Service keyring.
- An experimental, opt-in Secrets & Variables vault; **not independently audited** or positioned as a replacement for a dedicated password manager.

**Supported desktop:** Cinnamon on X11. Wayland, alternate desktop environments, unusual multi-monitor configurations and real video capture on every device have not been certified. A CI screenshot smoke test is not proof of flawless capture on physical hardware. See the [roadmap](ROADMAP.md).

## Install on Linux Mint

Visit [ClipMint Releases](https://github.com/cryogenized-spec/clipmint-linux/releases) and choose an explicitly published preview. Download the matching `clipmint_..._amd64.deb` and `SHA256SUMS` from **the same release**, verify the checksum, then open the `.deb` in Nemo and approve installation in Linux Mint's package manager.

The installer is a substantial download because it bundles Python, Qt and FFmpeg. **Check the displayed file size before downloading on metered mobile data.** Release-file SHA-256 verification detects mismatch/corruption, but **is not independent proof of publisher identity**: both the hash file and installer currently come from the same GitHub account. See [Security](SECURITY.md).

For a first install, there is no smaller package. For an existing installation, do not download a full installer merely to discover whether a small patch works.

## Verified preview updates and mobile-data safeguards

Open **Settings → Updates · verified preview channel**. Automatic checks and small-patch staging are **OFF by default**. After opting in, ClipMint may check the official public preview channel at most once every 24 hours. It automatically downloads **only** matching patches up to **20 MiB**. If no verified compatible patch is published, it reports the preview but **does not silently download a full installer**.

A differential patch requires the **exact installed base version** and its original matching `.deb` in ClipMint's private update cache or `~/Downloads`. The updater checks its SHA-256 and package identity, applies the patch, then verifies the reconstructed full installer. New releases may contain multiple patches for different base versions. Patches do **not** self-install or request `sudo`; package installation always requires separate approval.

Manual **Check for verified preview updates** only checks availability. **Download available preview…** may fall back to a large full `.deb`, and therefore shows an explicit confirmation with its size. Do not approve that download on a metered connection unless you intend to use the data.

Some older preview builds cannot read the current patch format. Certain releases provide an explicitly version-pinned **`clipmint-bootstrap-from-227.py`** script with **`BOOTSTRAP-SHA256SUMS`** for users who retained the matching Preview 227.1 installer. This script requests consent before fetching the small patch, reconstructs a full installer locally (which can be slow on hard drives), and leaves installation to Linux Mint. Use a helper **only for the exact version stated on its release page**. Never run an unverified script or assume a different `.deb` can act as its base.

## Privacy and data

Ordinary clipboard history is **plaintext by default**, held in a local SQLite database with owner-only file permissions. Basic password/token pattern filtering and application blocklists are best-effort safeguards, **not a guarantee** that sensitive material will never be copied. Pause monitoring when handling credentials.

You can opt into encrypted history through the desktop keyring. The old plaintext database is deliberately kept during migration as a recovery copy; after verifying migrated entries and making appropriate backups, use **Settings → Clipboard privacy → Verify and remove old plaintext history…** to remove it. Deleting files is **not** a forensic secure erase of backups or storage remnants. Treat this as a user-managed privacy decision.

The experimental vault encrypts entries locally using libsodium SecretBox and Argon2id. On X11, copying a secret to the clipboard may expose it temporarily to other local processes. Avoid storing high-value credentials until the vault has received independent review.

## Source development and tests

The packaged app does not run `pip`, `apt` or download dependencies on first launch. To work from a source checkout instead:

```bash
./install.sh --dev
./run.sh
```

Headless regression tests are run in GitHub Actions. With dependencies installed locally:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Real X11 selection, FFmpeg recording, and clipboard ownership need additional desktop integration testing; these cannot all be certified by headless Qt tests.

## Licence and attribution

Original current ClipMint source is licensed under **AGPL-3.0-only** ([full licence](LICENSE)). Earlier MIT-licensed code retains its existing permissions ([historical MIT licence](LICENSES/MIT-legacy.txt)). FFmpeg, Qt, fonts, and other libraries have independent licences and obligations. The character illustrations are **not automatically licensed under AGPL**; their redistribution rights remain to be established. See [Third-party notices](THIRD-PARTY-NOTICES.md).

Development history, obsolete preview notes and past draft PR discussions remain available in Git history rather than mixed into the current installation guide.
