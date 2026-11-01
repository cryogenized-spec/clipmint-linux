# ClipMint — a native Linux Mint app

ClipMint is a mouse-driven clipboard history, screenshot and area-video recorder for **Linux Mint 22 Cinnamon/X11**. It is independent of ClipClip and does not use Wine.

## Install: one file, no terminal

1. Open [Releases](https://github.com/cryogenized-spec/clipmint-linux/releases) in this private GitHub repository.
2. Download the newest **clipmint_0.2.0_amd64.deb** from a successful preview build.
3. Double-click the .deb file in Nemo and choose **Install Package** in Linux Mint's graphical installer.
4. Find **ClipMint** in your application menu. Open it whenever you want. There is no terminal to keep open.

The package bundles Python, Qt, and FFmpeg into the app. It does not use pip, apt, Wine, or runtime downloads on your laptop. It does not install any development libraries or change CopyQ. Building the downloadable .deb happens only on GitHub's machines. Do not use the old source ZIP or old install.sh as a user installer.

## How to use

Copy some text or an image. The history appears in ClipMint. Right-click a snippet to **Copy**, **Pin** or **Delete**. Select **Screenshot area** or **Record area** and drag a rectangle. Click **Stop recording** in the window or tray menu to save your MP4. No global shortcuts.

- Screenshots: ~/Pictures/ClipMint
- Videos: ~/Videos/ClipMint
- Local database: ~/.local/share/clipmint/history.sqlite3

## What is and is not verified

GitHub Actions builds the frozen app and runs Python/SQLite tests plus a launch test under virtual X11. Recording and screenshot capture must still be tested on an actual Linux Mint Cinnamon laptop. This is an **early preview**, not production tested.

## Privacy and limitations

The SQLite history is unencrypted. Pause monitoring before copying confidential data; delete saved secrets if they were captured. Video is silent (no microphone or system audio). Primary-display-only capture selection; no built-in OCR or annotation, and no Wayland support yet. The main ClipMint window may overlap the recorded area until you minimize or move it.

## Developers

The source tree contains Python and PySide6 code. The GitHub Actions workflow builds a .deb using PyInstaller and bundles a pinned, checksum-verified separate GPL FFmpeg executable downloaded on the **build runner only**. Original ClipMint code is MIT-licensed; FFmpeg follows its own GPL licence. This project is not affiliated with the original ClipClip.
