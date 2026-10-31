# ClipMint — Native Linux Clipboard & Capture

Early v0.1 prototype for **Linux Mint Cinnamon (X11)**. No Wine, no mandatory keyboard shortcuts.

ClipMint aims to combine persistent text/image clipboard history, searchable and pinned snippets, right-click **Copy to clipboard**, selected-area screenshots, and selected-area MP4 video recording in one mouse-driven PySide6 desktop app.

## Current status
The initial source archive has been prepared and basic Python syntax plus SQLite unit tests have passed. **The Qt GUI, area selection and actual video recording have not been tested on the target laptop.** Do not treat this as a production release.

## Stack
- Python 3 and PySide6 (Qt)
- SQLite for local clipboard history
- X11 and FFmpeg / libx264 for area capture
- Video output: `~/Videos/ClipMint`; images: `~/Pictures/ClipMint`

## Installing the source
Obtain the v0.1 source ZIP from the ChatGPT conversation and extract it. In the extracted project directory:

```bash
chmod +x install.sh run.sh
./install.sh
./run.sh
```

Inspect scripts before running. No administrator privileges needed to run the application; the installer may request sudo to install distro dependencies. The existing CopyQ configuration is not modified.

## Security and limitations
Clipboard history is stored locally and **unencrypted**. Avoid copying passwords while monitoring is enabled. Multi-monitor, rich text, annotation, OCR, audio capture and desktop-environment compatibility require additional implementation and testing.

This project is independent of, and not affiliated with, ClipClip.

## Next step
Import the remaining source files from the ClipMint v0.1 ZIP, then run the unit tests and test screenshot/video recording on Linux Mint Cinnamon.
