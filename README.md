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


## v0.5 review — keyboard, rich MIME, OCR, privacy (draft PR #10)

**Not a final release.** The GitHub source branch provides a native PySide6
quick-search popup, a best-effort local clipboard privacy filter, support for
plain text + HTML + PNG + Nemo file URI/cut data, and offline Tesseract OCR.

### Keyboard popup on Linux Mint Cinnamon X11

ClipMint runs as one instance with a local Unix socket. Launch
\`/opt/clipmint/ClipMint --toggle\` while it is running to summon the search
popup near the pointer. Within the popup type a fuzzy search, use arrow keys,
press Enter to paste the selected item or Ctrl+Shift+Enter to paste plain text.
Escape closes the popup. Other invocations signal the existing process; they
do not create another watcher. In Settings → Quick access, use **Register
shortcut in Cinnamon** to explicitly create a NEW custom Cinnamon binding
(default Ctrl+Alt+V). Conflicts with existing custom bindings are rejected
rather than overwritten. Standard Cinnamon bindings may still conflict; check
the native Keyboard settings if the hotkey does not fire. A copy-only fallback
remains available if xdotool cannot target the original X11 window.

The popup's automatic paste is **user-initiated**, following Enter, not a
blind background action. Terminal classes have a best-effort Ctrl+Shift+V
heuristic. X11 permissions do not provide safe source-app attribution, and
the popup does not claim to know whether the target field is sensitive.

### Capture types and privacy

ClipMint retains a **bounded MIME subset**, including text/plain, text/html,
PNG, text/uri-list and x-special/gnome-copied-files (the Nemo cut/copy format).
It round-trips these formats when copying an item from history. Old clipboard
entries continue to work without saved MIME bundles. Unsupported formats do
not become executable data. PRIMARY highlight selection remains OFF.

Concealed x-kde-passwordManagerHint=secret items and recognized password
manager-specific MIME targets are discarded before capture. Plain text
containing common credentials and Luhn-valid card numbers is excluded with
conservative pattern matching. Active-window exclusion is configurable, but
**cannot reliably prove clipboard origin on X11**, so it is not a guarantee.

**Encrypted clipboard history is optional, not automatically migrated.**
Settings → Clipboard privacy → Encrypt history initiates a separate,
user-approved migration. Entry bytes, saved HTML/file formats and searchable
preview text are authenticated-encrypted with libsodium; the random key is
stored in the desktop Secret Service keyring. History metadata such as time,
type, bin, count and pinned state remains visible. The old plaintext SQLite
history stays untouched as a recovery copy; users need to manage deletion
or backups of it themselves. If a previously enabled secure history key is
unavailable, automatic capture is disabled rather than falling back to
unencrypted history. This is not a security audit or a substitute for a
dedicated password manager.

### Screenshot and image OCR

Right-click any PNG image in the clipboard history and choose **OCR · Extract
text from image**. The screenshots library also offers OCR on right-click;
after taking a screenshot, the confirmation notice offers an OCR button too.
ClipMint sends PNG bytes directly to local Tesseract via stdin in a Qt worker
thread, without uploading images to a remote service or saving temp images.
Recognized text goes immediately into the **system clipboard**; if monitoring
is active and the text passes the sensitive-data filter, it is additionally
saved as a new text entry. Empty OCR results are reported, not saved.

The preview .deb requires \`tesseract-ocr\`, English trained data and
\`xdotool\` in addition to ClipMint's built-in Qt libraries. Language support
is English for this first version. Test with captured receipts and screenshot
text on the actual Mint/Cinnamon X11 desktop before relying on it.


## v0.6 development preview — Indexed search and productivity

This source-only preview builds on v0.5. **There is no production v0.6
release yet.** The approved full-size Kohaku card is tracked separately by
PR #11; this branch does not replace or fabricate that artwork.

### Search the content, not just the filename

The archive search now uses local SQLite **FTS5** to index the full text of
normal text clipboard items (up to 128 KiB per item), as well as saved
previews. Search for words occurring deep inside a previously copied
document, or several words at once. Choose **Best match** in the sort selector
to rank matches using SQLite relevance. Existing latest/oldest/alphabetical
sorts remain available. Punctuation and partial-preview searches still
receive the literal search fallback. The keyboard quick popup combines these
indexed results with typo-tolerant fuzzy matching.

On first run, ClipMint adds the FTS index to the **ordinary plaintext**
SQLite history database. The index is local, but it is also **plaintext**
because the existing history is plaintext. It never leaves your machine.
**Encrypted history does not create FTS tables**; that mode searches
decrypted previews only, in process memory, without indexing protected
clip bodies to disk. ClipMint will use literal preview search if SQLite lacks
FTS5. Back up the existing history folder before upgrading.

### Tags and favourites

Right-click a clipboard item to **Edit tags** or **Add to favourites**.
Tags are comma-separated letters, numbers, underscores and hyphens.
Use the tag dropdown and the **♥ Favourites** checkbox to narrow the archive.
Favourites are separate from pins: only **pinned** clips are protected from
automatic pruning by the existing retention policy. Tag labels and favourite
states are normal metadata, **not secret values**, even when encrypted history
is active. Avoid confidential words in tag names.

### Reusable snippets

Select **✧ Snippets** to create or edit plain-text templates, or right-click
a text clip and choose **Save as snippet template**. The literal placeholder
`{{customer}}` will prompt you for a value when you click **Fill & copy**.
No Python, shell expressions, scripting or network substitution is executed.

Templates are stored on this device. In ordinary history, template bodies
are plaintext; in optional encrypted history, their bodies are individually
authenticated-encrypted using the existing encrypted-history key. Template
**names** remain metadata. Avoid storing passwords in ordinary snippets.

### Preview-first text workshop

Right-click a text clip and choose **Text workshop**. Local operations include
trim/strip, remove or deduplicate blank/repeated lines, alphabetic sorting,
case conversion, JSON pretty printing/minification and URL encode/decode.
Check the preview, choose **Copy preview** or explicitly **Save as new clip**,
or use **Revert**. The original history entry is never modified.

### Multi-paste queue (explicit, no automatic typing)

Right-click one or more items and choose **Add to paste queue**, in the order
you need them. Click **NEXT N** to copy one queued item and paste it
yourself into the target application. Repeat for subsequent items. The queue
lives only in memory and resets when ClipMint quits. It does not inject
keystrokes, run macros, execute clipboard text or alter other windows.
A deleted clip is skipped. This is a safe staged-paste workflow, not a
background automation of multiple pastes.

### v0.6 preview installation and acceptance

After the branch CI completes, download the **ClipMint-v0.6-main-integration-preview**
GitHub Actions artifact, verify `SHA256SUMS`, and install the
`clipmint_0.6.0~preview1_amd64.deb` package via `sudo apt install ./...`.
First close ClipMint and back up `~/.local/share/clipmint` with SQLite WAL
files intact. The UI and integration tests run on headless Qt/Xvfb; you must
still confirm real Cinnamon/X11 search, history migration, keyboard paste,
Nemo and LibreOffice clipboard formats, screen capture and templates on the
HP OMEN before treating the preview as a daily-driver release.


## The approved full-body Kohaku character card (PR #11)

The approved original is `clipmint/assets/kohaku_card.png` (941 × 1672 pixels;
2,341,345 bytes; SHA-256 `585800ce776353d84a9d60e798ff591d06b580f95be0943a46ae67c1c107817a`). The full floral
frame and all Japanese, romaji, and English captions are part of this image.
The native Qt card preserves its aspect ratio without cropping or redrawing.
Builds, screenshots, and installer verification deliberately fail if it is
missing, altered, or substituted. The v0.6 indexed search, OCR, tags,
favourites, snippets, transforms, and controlled paste queue are preserved.

Before merging this PR, upload the exact original PNG at that path and
confirm all three checks are green. The release remains a development preview
until actual Cinnamon/X11 field acceptance and security review are complete.


## Screenshots gallery visual review (development only)

The separate \`feat/screenshot-gallery-preview\` review branch replaces the
filename-only Screenshots screen with an in-app PNG thumbnail grid and a
larger, aspect-preserving preview for the selected screenshot. Dimensions
and local file size appear below the preview. Double-click still opens the
file in its normal desktop application, and the selected-image **Open**,
**Edit** and **OCR** controls reuse the existing behaviours. The existing
Recordings page remains a filename list but now shares the same burgundy,
rose-gold and ivory archive styling.

Thumbnails are decoded locally in short batches, with image dimensions and
file size bounded to avoid unresponsive loading from damaged or enormous
screenshots. No images are uploaded, copied into clipboard history, or
changed on disk. Existing PNG files remain in \`~/Pictures/ClipMint\`.
Large/invalid files may show a preview-unavailable message; they remain
accessible in their original folder.

**This is a draft UI revision, not an installed update.** The
\`Review ClipMint screenshot gallery\` workflow runs Qt tests and publishes
a screenshot of the actual Qt screen using only synthetic image fixtures.
Review the rendered preview and test with real screenshots on Linux Mint
before merging or packaging a new release.


### Bilingual sidebar and Cinnamon screenshot keyboard shortcut (review branch)

All six sidebar entries now have a consistent English section name and a
short corresponding Japanese subtitle: Clipboard / クリップボード,
Screenshots / 撮影画像, Recordings / 画面録画,
Vault / 秘密保管庫, Autosort / 自動仕分け, Settings / 設定.

**Ctrl+Shift+S** configured in the old Settings → Keyboard shortcuts is a
*window-local* Qt shortcut, not an OS-wide replacement. This branch adds
a separate **Settings → Screenshot area · global shortcut** control.
Click **Register screenshot shortcut in Cinnamon…** to explicitly bind
the chosen global key to \`/opt/clipmint/ClipMint --screenshot-area\`.
The command sends a local \`screenshot-area\` instruction to the existing
ClipMint process; if ClipMint is not running, it starts ClipMint and opens
its own area selector. It does **not** launch the default screenshot utility.

ClipMint will never silently overwrite another Cinnamon custom shortcut or a
known built-in screenshot key. If the key is already assigned, first change
that binding in **System Settings → Keyboard → Shortcuts**, then register
the ClipMint shortcut. Other applications and desktop extensions may own keys
that Cinnamon's standard GSettings registry cannot detect; verify the binding
physically on Linux Mint Cinnamon X11. Disable or remove the custom binding
using Cinnamon's Keyboard settings if reverting. The original
\`Ctrl+Shift+S\` in-window shortcut stays available.
