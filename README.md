# ClipMint ve-02 / v0.3.0 — Linux Mint Desktop Preview

A mouse-first clipboard manager, screenshot tool, and dedicated MP4/GIF recorder for **Linux Mint 22 Cinnamon X11, x86-64**. Independent of Windows ClipClip; no Wine.

**Current source-code licence:** [GNU AGPLv3, version 3 only](LICENSE) (`AGPL-3.0-only`). Earlier MIT-licensed releases keep their original permissions; bundled fonts, FFmpeg, dependencies and art have their own rights. See [third-party notices](THIRD-PARTY-NOTICES.md).

## Install normally, no terminal

1. Open [ClipMint Releases](https://github.com/cryogenized-spec/clipmint-linux/releases).
2. Download the `clipmint_X.Y.Z_amd64.deb` attached to the chosen version tag (`vX.Y.Z`), along with `SHA256SUMS`. You can verify both files from their download folder using `sha256sum -c SHA256SUMS`.
3. Double-click the file in Nemo and choose **Install Package**.
4. Open **ClipMint** from the application menu. No terminal remains open.

For developers working from a source checkout, run `./install.sh --dev` once
to create a local `.venv` and install Python dependencies, then start with
`./run.sh`. This is separate from the standalone installer and intentionally
requires an explicit developer opt-in. OCR is optional: Tesseract and the
English language pack are recommended, but not required to run ClipMint.
Without Tesseract, OCR actions report that the optional tool is missing.

The installer bundles Python, Qt, and FFmpeg. GitHub downloads build-time dependencies on the **GitHub runner**, not on your laptop. The app doesn't run pip/apt or fetch packages on first use.

## Automatic preview updates (new bootstrap release)

After installing the first version that includes the updater, open
**Settings → Updates · verified preview channel**. The
**Check for and download verified preview updates automatically** checkbox
defaults to **ON** and can be switched off. The app checks the official
`cryogenized-spec/clipmint-linux` GitHub **preview releases** no more than once
per 24 hours (with a manual **Check for updates now** option). A successful
`main`-branch build can now publish an **immutable, public GitHub prerelease**
containing an `amd64.deb` and its `SHA256SUMS`.

Updates download to a private user cache only after version validation. The
client verifies the GitHub release URL, the SHA-256 checksum and the .deb's
internal Package/Version/Architecture identity before offering it for install.
There are no update-server credentials, untrusted shell commands, package
hooks, or automatic privileged installation. A normal GitHub login is **not**
needed to check or download updates. Network access is required only for update
checks and downloads; all existing clipboard functions remain local.

**Important distinction:** ClipMint can **automatically check and download**,
but it cannot silently replace a system-owned `/opt/clipmint` installation.
Select **Open verified installer in Linux Mint…**, approve the installation
in your native package manager, and then fully **Quit ClipMint and restart** it.
Closing its main window only hides it; the previous background process remains
active until you quit. If you enabled **Clear unpinned Temporary clips when I
quit ClipMint**, disable that option first if you want to retain those entries.

This updater is **not retroactively present in older installed .deb files**.
Install this bootstrap .deb **once**; subsequent updates can be found and
downloaded from inside the application. ClipMint's preview update channel uses
`clipmint-preview-NUMBER-ATTEMPT` release tags; official stable releases remain
separate and are not silently replaced with a downgrade.

## Background clipboard history

**Closing the ClipMint window keeps the clipboard watcher running.** New, permitted
text copies continue to be written to the local SQLite history, even if the
Cinnamon panel has no compatible tray icon. The installed app launcher opens
the existing window rather than starting a second watcher. The tray icon,
when available, also provides a Show command.

In **Settings → Start at login**, you can explicitly opt in to launching the
hidden watcher after signing into Cinnamon X11. This is **OFF by default**.
The **Quit ClipMint · stop background monitoring** action in Settings, the
tray's Quit action, and `ClipMint --quit` intentionally terminate the process
and stop capture. No clipboard history can be collected while ClipMint is
actually terminated, the user session is logged out, or the computer is off.
Potential credentials and concealed MIME payloads are deliberately excluded.

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

## Optional removal of plaintext history after encryption

**Encrypting history does not automatically delete the original SQLite file.**
After enabling encrypted history and confirming it is readable, Settings offers
**Verify and remove old plaintext history…**. ClipMint checks legacy clip
contents, metadata, tags and templates against the authenticated encrypted
archive before showing an explicit permanent-deletion confirmation. If the
check fails, it leaves the original file untouched. The action removes only
the old `history.sqlite3` database and its SQLite sidecars; it does not
remove backups, keyring data, snapshots or other copies, and **cannot guarantee
forensic erasure from an SSD**. Backup your encrypted archive and keyring
separately before confirming removal.

## Verification and limitations

Automated tests cover SQLite bins/migration, UI launch and screen-recorder state where possible. GitHub Actions performs a frozen Qt/X11 start test and verifies the included FFmpeg has X11 capture and H264 encoders. **Actual capture on the HP OMEN / Mint Cinnamon has not yet been field-tested.** X11, single-primary-screen selector only; not Wayland. This is a preview, not a security-hardened release.

## Licences

The currently published ClipMint-owned source code is licensed under the **GNU Affero General Public License, version 3 only** (`AGPL-3.0-only`); see [`LICENSE`](LICENSE). Previously distributed MIT-licensed copies and the rights already granted for those releases remain valid. The historical MIT text and copyright notice are kept in [`LICENSES/MIT-legacy.txt`](LICENSES/MIT-legacy.txt) for attribution and provenance, not as a new dual-licensing promise for future changes. Bundled FFmpeg, PySide6/Qt and other Python dependencies, SIL OFL fonts, and supplied artwork are **not automatically relicensed** by ClipMint's AGPL declaration. See [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) and the copyright/licence files inside the Debian package. The corresponding ClipMint build source is publicly available at https://github.com/cryogenized-spec/clipmint-linux; the `.deb` contains a source pointer and build commit.


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

On a **fresh installation of this development branch**, Autosort starts
**enabled**, with 30 editable Smart-type rules and grouped destination
collections: Writing, Web, Development, Data, Contacts, Media, Utilities,
Templates and Finance. Each recognized ordinary clip is routed to its
collection and tagged with its specific type (e.g. `type_json` or
`type_tracking_urls`). This creates navigable categories without introducing
30 tiny collection tabs. On upgrades, **an explicitly saved custom rule list
or on/off preference is preserved**; nothing is silently overwritten.

The 30 built-in detections cover plain and rich text, Markdown, web/tracking
URLs, code, shell commands, JSON, YAML/XML, OTPs, passwords, API tokens,
email, phone and postal addresses, payment cards, bank accounts, public crypto
wallet addresses, images, SVG, colours, CSV/TSV, paths, copied files, parcel
tracking, dates, logs, hashes, math/LaTeX and reusable templates.

Sensitive classifications (**password/master key, OTP, API key, payment-card
data, bank routing/account**) are discarded *before* normal and encrypted
history writes, even if Autosort is switched off or a custom rule tries to
retain them. No credential is automatically imported into the separately
encrypted Vault. An isolated 6–8-digit number is treated as a possible OTP
and excluded; this may also exclude ordinary numerical references. Bare
random 40+ character hexadecimal strings are excluded because a checksum
is indistinguishable from a secret key without context. Heuristics are
best-effort and may have false positives/negatives. When ClipMint sees a
recognised sensitive clipboard text value, it schedules a **30-second
conditional clear**: it empties the X11 clipboard only if the value is
unchanged, so copying something else is not lost. The timer is memory-only;
quitting ClipMint or another clipboard manager can defeat expiry, and local
X11 processes may read the value before it clears. Neither omitting history
nor a clipboard timer is secure destruction or a substitute for a credential
manager.

Autosort can still be disabled, reordered, and customised using Text, Image,
URL, Phone, Keyword, Regex or **Smart** rules. The first enabled matching
rule wins for ordinary content, and unmatched items stay in the selected bin.
New custom rules are inserted before the broad plain-text fallback.
**Restore 30 defaults** explicitly replaces rules after a confirmation; it
does not move, erase or retag existing history. Preset routing only affects
new clips. No remote link previews, external address-book lookups, executable
CLI commands, live package tracking, payment processing or cloud calls are
performed by classification. The advanced per-format utilities in the user's
feature brief (tree views, rendering, QR generation, etc.) are separate future
UI features, not part of this detector PR.

Regular expressions remain capped at 200 pattern characters, 8,192 input
characters and a short execution timeout. Clipboard source-app attribution
is not reliably available from Linux Cinnamon/X11; confidence is therefore
heuristic. Use the **Test selected history clip** control to inspect what a
newly captured entry would be classified as.

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

Download the **ClipMint-v0.6-main-integration-preview** GitHub Actions
artifact from the **latest successful build**, not an older PR run. Verify
`SHA256SUMS` beside the `.deb`. Preview packages now have a **unique**
Debian version, `0.6.0~preview1.RUN.ATTEMPT`, so a newer build replaces the
previous one; the constant `0.6.0~preview1` version used on earlier builds
could leave the old code installed.

**Important: quit the running ClipMint process before installing or testing
an upgrade.** Merely closing the main window leaves its background clipboard
daemon running. The updated executable forwards Cinnamon screenshot shortcuts
to that *existing* (possibly older) process, so changing the installed files
cannot update capture behaviour until the daemon exits. In Settings, use
**Quit ClipMint · stop background monitoring**, or use the tray's Quit action.
If you enabled **Clear unpinned Temporary clips when I quit ClipMint**, turn
that option off first if you want to keep those items; deliberate Quit can
otherwise remove them. Do not forcibly kill the database process while it is
writing. A package installation does not silently quit the app or delete data.

Install the downloaded `.deb` in a folder containing only that installer,
then verify the *installed* version (which must match its filename):

```bash
sudo apt install ./clipmint_0.6.0~preview1.*_amd64.deb
dpkg-query -W -f='${Version}\n' clipmint
```

After installation, start ClipMint again from the Cinnamon menu. Test
Ctrl+Shift+S while Firefox is in front. A completed screenshot should be
immediately pasteable with Ctrl+V; only the small Edit / OCR popup should
appear, **not the main ClipMint window**. If an old preview has the identical
version, `sudo apt install --reinstall ./<exact-filename>.deb` is required to
replace it. Never infer that a build is installed solely because GitHub CI
passed.

For recovery, back up `~/.local/share/clipmint` with SQLite WAL files intact
after quitting. The UI, Qt and Xvfb integration tests cannot establish that
every Cinnamon or Firefox configuration will behave identically; still test
real clipboard ownership, focused-window behaviour, search, Nemo and
LibreOffice formats, capture and templates on the actual Linux Mint machine
before treating the preview as a daily driver.


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

ClipMint never silently overrides another shortcut. It checks the Cinnamon
media-key, window-manager and custom-shortcut registries before registering
and verifies the final binding afterward. If a **built-in screenshot** action
owns the desired shortcut, ClipMint explicitly asks whether to give it priority.
If approved, only the conflicting combination is disabled, all other keys
remain assigned as before, and a local restoration backup is written to
`~/.config/clipmint/cinnamon-keybinding-backups.json`. Use **Restore previous
Cinnamon screenshot binding…** to reverse the takeover (unless an independent
user edit would be overwritten). Other system or custom shortcut conflicts
require manual reassignment in **System Settings → Keyboard → Shortcuts**.

The new optional global **recording** shortcut (`Ctrl+Shift+R`) starts MP4
region selection from outside ClipMint. The clipboard popup global shortcut
(`Ctrl+Alt+V`) continues to open quick search. In-app search, copy and
monitoring shortcuts intentionally remain *window-local*: taking global
ownership of Ctrl+F and Ctrl+C would disrupt other applications.

Use **Check Cinnamon hotkey assignments…** for a read-only report of the
screenshot, recording and popup shortcuts. A Cinnamon global keybinding
normally takes precedence over a focused application's local hotkeys, but
another shortcut daemon or desktop extension may still interfere. Test by
pressing the keys while another app is focused on your Linux Mint Cinnamon
X11 desktop. No shortcuts are replaced during installation without approval.


### Vault: one-click masked copy (review)

After unlocking the encrypted vault, select an entry and choose **Reveal**.
The value remains hidden as password dots unless **Show value** is explicitly
enabled. The dialog now includes its own **Copy** button, which copies the
**entire** saved value without needing to select any characters, even while
the value remains masked.

The existing Copy action in the vault list uses the same full-value clipboard
path. Both show a temporary check mark (\`✓ Copied!\`) on the clicked button
and the status bar shows only \`Copied!\`. The clipboard is cleared after
30 seconds **only if its contents are unchanged**; copying from the vault
never adds the value to the normal ClipMint history or search index.
The usual X11 clipboard-security limitation still applies while the value
is available for pasting. These changes do not alter the vault encryption.


## Clipboard secret-detection hardening — review branch

The proposed \`fix/clipboard-secret-detection\` branch adds a single, local detector
used by clipboard MIME capture, direct plaintext-history writes, OCR and snippet
UI checks. It detects password-manager hints, known token formats, private keys,
credential assignments, Luhn-valid payment-card numbers, and sufficiently
random-looking standalone strings. On a match it **does not retain the value**
in ordinary history, previews, file-format bundles, or the plaintext search index.
ClipMint shows only a non-revealing "not saved" status.

**No automatic secret import into the vault is attempted.** That would turn
untrusted clipboard captures into retained credentials without an explicit choice.
The \`mask()\` helper is deliberately a fixed-length placeholder, not encryption
or a promise that the source application or X11 system clipboard is protected.

This filter has both false positives (e.g. some hexadecimal hashes) and false
negatives. Source-application hints are best-effort, not an access-control
boundary. It is a review-only change until tests and a packaged Linux Mint
field check pass. It **does not retroactively remove** credentials already
recorded in \`~/.local/share/clipmint/history.sqlite3\`, previous backups,
SQLite WAL pages, or the plaintext FTS index. Review old history locally and
rotate any credentials suspected of exposure; do not paste live secrets into
GitHub issues, bug reports, or test fixtures.


## Temporary collection: optional retention (development review)

**Default: OFF.** Settings → **Temporary collection · retention** exposes
two independent, opt-in choices:

- **Automatically remove unpinned Temporary clips after 24 hours.** Requires
  explicit confirmation when enabling; already-expired entries are removed
  then, and the application checks periodically while running (every five
  minutes). For an already-enabled setting, expiration also runs on startup.
- **Clear unpinned Temporary clips when I quit ClipMint.** Runs only on an
  orderly, deliberate application exit (Quit in the tray or closing when there
  is no tray), **not** when hiding its window to the tray. An app crash,
  forced termination or package update does not invoke the exit cleanup.

Both protect **pinned entries**. Neither touches the Work or Personal bins,
other user-created collections, reusable snippet templates, screenshot files,
vault data, or other application files. Moving an old item into Temporary
subjects it to the selected age rule using the item's existing last-copied
timestamp. Turning a rule off stops that cleanup without purging anything;
existing saved settings are preserved on upgrade, and no existing user is
silently opted in. Deletions remove full-text search entries in ordinary
history too. Expiry is measured against UTC timestamps, not a guessed local
clock or application installation date. Recopying the same newest entry
refreshes its last-used timestamp (for both ordinary and encrypted history),
so a recently reused Temporary item is not removed using its older date.
Choosing **Copy** in the archive, using the quick-search popup, or copying
from the Multi-Paste Queue also renews the 24-hour retention clock.
Expired clip IDs are dropped from the paste queue and quick-popup cache
before another copy could reuse a SQLite row ID. For plaintext history, a
cleanup rebuilds FTS5 postings and compacts the SQLite file to reduce old
search-index remnants; this may briefly use extra CPU on large archives.

**Caution:** These settings deliberately remove eligible history records.
Enabling the age rule warns before removing previously expired entries.
SQLite deletion and WAL cleanup reduce recoverable remnants but cannot
guarantee physical secure erasure on SSDs, backups or OS snapshots. This is
a draft feature and is not available in the current installed release.

## Verified one-click clipboard archive backup (review branch)

Settings → **Clipboard privacy → Backup clipboard archive…** saves a
consistent single-file SQLite snapshot of the **currently active** archive
via Python's built-in SQLite online backup interface. It captures
committed changes even when the source database is open and using WAL.
The saved .sqlite3 has owner-only 0600 file permissions and is verified
using PRAGMA integrity_check before the staged file is placed at the
selected destination. If a destination already exists, it is *never*
overwritten without an explicit confirmation. A cancelled or failed backup
does not modify the original database.

**Plaintext history produces a plaintext backup**, and the app asks you to
acknowledge this risk before saving. **Encrypted history stays encrypted**
without copying or exposing its keyring key; a different computer cannot
read it without the original key. The separately encrypted Vault and the
application's QSettings are **not** included. This operation is export-only;
replacing or restoring a live archive requires its own validated restore
workflow, and is not part of this draft. No cloud sync, shell command, or
network access is used.

## Optional launch at login (development branch)

Settings → **Start at login → Launch ClipMint when I log in** is **OFF by default**.
With an installed .deb, enabling it creates only
`~/.config/autostart/clipmint.desktop` for the current user (mode 0600).
It starts `/opt/clipmint/ClipMint --hidden` on subsequent Cinnamon/X11 logins.
If a tray is available, the app stays in the tray; otherwise it opens its
window so it cannot become an inaccessible background process. Launching
again does not create another clipboard watcher or force the running window
to appear. Turning the setting off removes only ClipMint's exact managed
entry. Existing custom entries and symlinks are never overwritten or removed,
and the installed executable is checked before enabling. A crash or package
update cannot opt you into login startup. No system-wide autostart files
or other users' configuration are changed.

This remains a **review feature** until CI passes and Cinnamon/X11 startup,
tray and logout behaviour are tested on the HP OMEN.

## Clipboard history hardening (draft PR)

A separate history-hardening draft introduces \`0700\` permissions on the managed
\`~/.local/share/clipmint\` directory and \`0600\` on the history SQLite
database (including upgrades from permissive modes), with
\`PRAGMA secure_delete=ON\`. Deleted clips are removed from the full-text
index, committed, and followed by a \`wal_checkpoint(TRUNCATE)\` to avoid
leaving ordinary WAL remnants indefinitely. The optional
\`ClipStore.compact_history()\` maintenance operation performs a checkpoint,
\`VACUUM\`, and another checkpoint; it can be expensive with large images
and must be invoked intentionally, not on every copy.

Copying **A → B → A** now refreshes the *existing* record's recency and
last-used timestamp rather than inserting another A. Identity, pinned state,
favourites and user tags survive. The recency sequence also controls the
unpinned LRU retention limit and survives reopens and migrations.
Encrypted history uses keyed HMAC fingerprints; cleartext/hashes of
possible passwords are not written into its metadata. Existing encrypted
archives receive a one-time fingerprint backfill at unlock; a large
image-heavy archive may take longer to open that first time. Entries that
fail ciphertext authentication are **preserved but hidden** from ordinary
search so one corrupted record cannot prevent access to healthy items. A
visible warning reports detected damaged entries; manual recovery is
necessary, and no plaintext fallback is enabled.

**Privacy limitation:** SQLite secure-delete, VACUUM and WAL truncation
reduce remnants inside the active database. None of these can guarantee
physical erasure from SSD flash cells, snapshots, backups, swap, other
applications or previously generated copies. This change neither removes
existing plaintext legacy history after an encrypted migration nor changes
the retention policy, snapshot/export behaviour, or current package release.
Do not treat it as a guarantee that a secret once recorded is unrecoverable.
