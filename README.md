# ClipMint ve-02 / v0.3.0 — Linux Mint Desktop Preview

A mouse-first clipboard manager, screenshot tool, and dedicated MP4/GIF recorder for **Linux Mint 22 Cinnamon X11, x86-64**. Independent of Windows ClipClip; no Wine.

## Install normally, no terminal

1. Open [ClipMint Releases](https://github.com/cryogenized-spec/clipmint-linux/releases).
2. Download **clipmint_0.3.0_amd64.deb** from the latest successful preview release.
3. Double-click the file in Nemo and choose **Install Package**.
4. Open **ClipMint** from the application menu. No terminal remains open.

The installer bundles Python, Qt, and FFmpeg. GitHub downloads build-time dependencies on the **GitHub runner**, not on your laptop. The app doesn't run pip/apt or fetch packages on first use.

## Clipboard bins and sorting

Three independent bins — **Work**, **Personal**, and **Temporary** — are provided. Click **+** to create further bins (up to 32-character names). New copied snippets go into the currently selected bin. Right-click an entry to Copy, Pin, Move to another bin, or Delete. Double-click to copy.

**View:** All, Text, URLs, Phone numbers, or Images. **Sort:** Latest first (default), Oldest first, A–Z, Z–A, or Numbered list. Search is scoped to the active bin. Pinned items remain in chronological order unless explicitly filtered or re-sorted.

Your old v0.2.0 history database is automatically migrated without erasing entries; old entries are assigned to Work. Data is stored in `~/.local/share/clipmint/history.sqlite3`. Clipboard entries are currently **unencrypted**. Obvious password/token assignments are skipped, but detection is incomplete and is not a security boundary. Use **Settings → Pause monitoring** when copying credentials. The Secrets & Variables page is an informational placeholder, **not** a password vault.

Autosort currently classifies previews as URLs, phone numbers, text and images for filters. Custom sort rules and variable templates are not implemented in this preview. The upcoming editable rules engine is tracked in [v0.4 roadmap issue #2](https://github.com/cryogenized-spec/clipmint-linux/issues/2).

## Screenshots and screen recording

In the **v0.4 development branch**, the **Screenshot Area** button defaults to mouse-dragging a capture rectangle; its **▾** menu retains a **Full screen** action. A noncaptured on-screen instruction overlay says to click and drag, release to confirm, or use Esc/right-click to cancel; selected width and height are shown during drag. Screenshots are saved to `~/Pictures/ClipMint` and can be opened from the Screenshots section.

Choose **Start Recording MP4 / GIF** or use its **▾** for GIF. The ClipMint main window hides. Click and drag the recording region. A **separate floating recorder window** appears: choose High/Medium/Low quality, choose MP4 or GIF, and click **Start recording**. The same button then says **Stop recording** and shows elapsed time plus an **approximate** estimated file size. After FFmpeg finishes, a **Save this clip?** dialog appears: **Yes (Save)** is selected by default; **Enter** saves and **← / →** switch focus to No. The No option discards the pending recording. Saved files are in `~/Videos/ClipMint`. File size shown during capture is an estimate, not a storage quota or exact output size.

The recorder tries to place the floating controls outside the captured rectangle. For fullscreen capture with no free space, the controls may appear in the footage. When the capture is running, do not forcibly terminate ClipMint or power off the system; unexpected termination may leave an unfinished hidden `.pending-recording-...` file behind. No microphone or system audio support yet.

## v0.4 UI development preview

On the isolated v0.4 development branch (not the v0.3 release), selecting an image in Clipboard shows an in-memory, aspect-ratio-preserving thumbnail in the PREVIEW pane with its dimensions. Text snippets still show text, with no automatic copy on click. The QSS style is being simplified using tonal dark surfaces, a distinct mint selected-state accent, and flat bin tabs; the UI remains native PySide6/Qt, not Electron. These changes require the project's GUI/CI tests and physical review on Linux Mint before a release. The **Secrets & Variables** feature is **not encrypted or enabled yet**. Do not store credentials in clipboard history.

## DotGothic16 display identity (v0.4 development branch)

ClipMint uses **DotGothic16** for the brand masthead and selected navigation/header elements. A custom native Qt `QPainter` wordmark draws three intentionally misregistered ink passes: **pink `#FF5AB3`**, **lime `#B9FF45`**, and **off-white `#F1F5F9`**. This effect is deliberately restricted to the heading; ordinary clipboard text stays in an accessible, single-colour font. Qt stylesheets (QSS) set the rest of the palette and spacing, rather than browser CSS or an Electron frontend.

The independent open-licensed DotGothic16 TTF and OFL license are fetched **only on GitHub's build/test runners** and integrity-checked against the original Google Fonts git blobs. The packaged application loads its local copy with `QFontDatabase`; it **never downloads fonts at launch**. A system-font fallback is used for unbundled developer checkouts. The packaged `.deb` includes the SIL OFL 1.1 licence. DotGothic16 is © 2020 The DotGothic16 Project Authors; [source and licence](https://github.com/google/fonts/tree/main/ofl/dotgothic16).

## Katakana and original manga details (v0.4 draft)

ClipMint's brand header adds `クリップミント` (the Japanese phonetic rendering of ClipMint), the image-preview caption adds `プレビュー` (preview), and the sidebar portrait is labelled `メイド / 01` (maid). Main controls and settings remain English for usability.

The sidebar displays the **crimson-haired maid selected by the user**, looking over her shoulder with her hands held behind her back, wearing a dark ruffled dress with white trim and red ornaments. `clipmint/assets/crimson_maid.png` is a 440-pixel-wide optimized PNG derived from the exact user-provided illustration, retaining its transparent background and compositing correctly on the dark Qt interface. The display widget shows a non-distorted upper-body crop. The image is bundled into the offline installer; no network transfer, third-party hosting, image-generation step, or downloaded font is required at runtime. It is decorative, cannot intercept clicks or keyboard focus, and hides when the window is too short. The older Koma mascot, sketches and JPEG assets are retired.

## Verification and limitations

Automated tests cover SQLite bins/migration, UI launch and screen-recorder state where possible. GitHub Actions performs a frozen Qt/X11 start test and verifies the included FFmpeg has X11 capture and H264 encoders. **Actual capture on the HP OMEN / Mint Cinnamon has not yet been field-tested.** X11, single-primary-screen selector only; not Wayland. This is a preview, not a security-hardened release.

## Licences

Original ClipMint code: MIT. Bundled FFmpeg: separate GPL executable, licence/source details inside the package. The included original DotGothic16 font is under SIL OFL 1.1; its licence is packaged as `OFL-DotGothic16.txt`.


## v0.4 development preview — NOT YET RELEASED

The Crimson Archive visual redesign, selected-image preview, region-selection
instructions, keyboard shortcut editing, Autosort and encrypted vault are in
stacked **draft** pull requests #4–#7. They are **not part of the installed
v0.3 release** and must not be used to assume existing clipboard history is
encrypted. The working v0.3 remains the fallback until full Linux Mint X11
acceptance and security review.

### Keyboard shortcuts

Settings contains Qt-native editable **window-local** keybindings (search,
screenshot area, video region, copy selected, and pause monitoring). Reset
restores the default; Disable clears one binding. Duplicate sequences are
rejected. Keys are not grabbed system-wide from other programs, and every
action remains available with the mouse.

### Autosort

Enable Autosort explicitly (it is OFF by default). Add, edit, disable, delete,
or reorder top-to-bottom rules to route new clips by type, URL, phone, keyword
or regex. The first enabled match wins; unmatched clips still go to the active
bin. You can set a matching rule to **Never capture**. Existing clips are not
retroactively moved or deleted. Regular expressions have a short execution
timeout; inputs longer than 8,192 characters are not matched by regex rules.
Clipboard source-application attribution is not reliably supported by this
version. Test a currently selected history clip before enabling complex rules.

### Secrets & Variables — experimental, needs independent security review

The vault is opt-in and stored at
\`$XDG_DATA_HOME/clipmint/secrets.vault\` or
\`~/.local/share/clipmint/secrets.vault\` when XDG_DATA_HOME is not set.
It stores encrypted entry names, types and values with libsodium SecretBox
(XSalsa20-Poly1305 authenticated encryption) and an Argon2id password-derived
key. The key is not stored on disk. Vault files and encrypted backups are
written with file permissions \`0600\`; the vault is locked at startup and on
window close, or after five minutes without a vault action.

To use it, create a vault with a unique passphrase of at least 12 characters,
then unlock it when you need a value. Add named Secret or Variable entries,
Reveal an entry only when needed, or Copy with an automatic 30-second
**conditional** clipboard clearing action (it only clears when the value is
still the copied secret). Create an encrypted backup from the vault screen
and keep it separately. You may restore a backup only when no vault already
exists, using the original passphrase. Changing the passphrase re-encrypts
the data with a new salt; create a new backup afterwards.

**No passphrase recovery exists**. Losing your passphrase means losing access
to the entries, even when you retain an encrypted backup. Deleting the vault
file does not erase external backups or guarantee SSD forensic erasure.

**Threat limitations:** ordinary clipboard history remains unencrypted.
Clipboard contents may be read by other processes on X11 while copied.
Python-managed memory cannot be promised to be securely wiped on locking.
The clipboard sensitivity detector is only a heuristic, not a guarantee.
Never assume this experiment is a production-grade credential manager until
security review, real laptop acceptance and frozen-package tests pass.

All vault tests use fake data. The app does not upload vault data or collect
secrets automatically from clipboard history.
