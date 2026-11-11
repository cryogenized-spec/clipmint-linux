# ClipMint 0.6.0 — draft public beta release notes

> **DRAFT ONLY — not an approved general-public beta announcement.** Release only after all gates in [RELEASE-CANDIDATE-v0.6.0.md](RELEASE-CANDIDATE-v0.6.0.md) and [PREVIEW-340-ACCEPTANCE.md](PREVIEW-340-ACCEPTANCE.md) have been met. Replace the version and checksum below if the final validated candidate differs from Preview 340.

## ClipMint: a local clipboard and capture workspace for Linux Mint

ClipMint brings searchable text and image clipboard history, collections, screenshots and region video recording together in a native Linux desktop application. This beta is for **Linux Mint 22 / Cinnamon / X11 / x86-64**. It uses no Wine.

### Highlights

- Searchable clipboard history for text and supported images, with collection filters, pinning and privacy controls.
- Region screenshots and MP4/GIF screen recording, with save/discard controls.
- Configurable global shortcuts and a quick clipboard popup.
- Faster cold screenshot/recording activation and sidebar navigation; history count and footer repaint improvements.
- Always-visible history type badges, full-resolution **Copy image** from screenshot gallery, and native copy-only drag of supported history content to other applications.
- Optional Tesseract OCR, optional desktop-keyring encrypted clipboard history, and an **experimental, unaudited** local secrets/variables vault.
- Locally stored data; no developer analytics or cloud sync required.

### Installation and package size

Reference package (for acceptance testing only): `clipmint_0.6.0.preview1.340.1_amd64.deb` — **122,116,552 bytes (about 122.1 MB)**. Download the `.deb` **and** `SHA256SUMS` from the [same GitHub prerelease](https://github.com/cryogenized-spec/clipmint-linux/releases/tag/clipmint-preview-340-1). In the folder containing both files, run `sha256sum --check SHA256SUMS`. The GitHub-reported package SHA-256 is:

`a0f4c393bbe5aef399a9d5d683d862ab2b47c5b227fa135ea2fa062e2745391e`

Back up existing ClipMint data before upgrading. Open the downloaded `.deb` in Nemo and authorize any installation in the native Linux Mint package manager. Package dependencies may require separate system-package downloads. Installer hashes prove integrity relative to the GitHub release; they do **not** independently authenticate the publisher.

### Updates and metered data

Preview update **checks** are manual by default, with optional availability checks no more than once every 24 hours. This manual-update beta does **not** download or stage update files in the background. A manual Download requires explicit approval and warns about the possible full installer transfer. If the exact old installer is available, ClipMint may reconstruct a newer package using a smaller patch; a full `.deb` download remains a possible fallback. No update self-installs.

### Known limits and privacy

Supported and tested target is Cinnamon/X11, not Wayland or Firefox-style cross-platform support. Hardware-specific video capture, drag-and-drop targets, multi-monitor scaling and responsiveness still require physical Mint testing. Clipboard history is plaintext by default; encryption is optional and sensitive-content filtering is best effort. The vault is experimental and has not undergone an independent security audit. X11 clipboard contents can be read by other local processes.

Application code is AGPL-3.0-only with preserved earlier MIT notices; bundled components and illustrations have separate rights. Public launch must remain blocked until artwork redistribution authorization is documented or any unlicensed artwork is replaced ([#95](https://github.com/cryogenized-spec/clipmint-linux/issues/95)). Independently signed release manifests remain a planned security improvement ([#63](https://github.com/cryogenized-spec/clipmint-linux/issues/63)).

### Feedback

Please report reproducible problems through [GitHub Issues](https://github.com/cryogenized-spec/clipmint-linux/issues), including OS version, X11 session details and synthetic reproduction steps. **Do not attach real clipboard databases, passwords, customer content or private captures.**

### Release authorization

Physical Mint acceptance: **pending**. Artwork rights: **pending**. Candidate freeze: **pending**. Approved public beta version: **not assigned**.
