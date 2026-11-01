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

Autosort currently classifies previews as URLs, phone numbers, text and images for filters. Custom sort rules and variable templates are not implemented in this preview.

## Screenshots and screen recording

The **Screenshot** button captures the entire primary screen. Its **▾** menu lets you instead select a rectangle with a mouse. Screenshots are saved to `~/Pictures/ClipMint` and can be opened from the Screenshots section.

Choose **Start Recording MP4 / GIF** or use its **▾** for GIF. The ClipMint main window hides. Click and drag the recording region. A **separate floating recorder window** appears: choose High/Medium/Low quality, choose MP4 or GIF, and click **Start recording**. The same button then says **Stop recording** and shows elapsed time plus an **approximate** estimated file size. After FFmpeg finishes, a **Save this clip?** dialog appears: **Yes (Save)** is selected by default; **Enter** saves and **← / →** switch focus to No. The No option discards the pending recording. Saved files are in `~/Videos/ClipMint`. File size shown during capture is an estimate, not a storage quota or exact output size.

The recorder tries to place the floating controls outside the captured rectangle. For fullscreen capture with no free space, the controls may appear in the footage. When the capture is running, do not forcibly terminate ClipMint or power off the system; unexpected termination may leave an unfinished hidden `.pending-recording-...` file behind. No microphone or system audio support yet.

## Verification and limitations

Automated tests cover SQLite bins/migration, UI launch and screen-recorder state where possible. GitHub Actions performs a frozen Qt/X11 start test and verifies the included FFmpeg has X11 capture and H264 encoders. **Actual capture on the HP OMEN / Mint Cinnamon has not yet been field-tested.** X11, single-primary-screen selector only; not Wayland. This is a preview, not a security-hardened release.

## Licences

Original ClipMint code: MIT. Bundled FFmpeg: separate GPL executable, licence/source details inside the package.
