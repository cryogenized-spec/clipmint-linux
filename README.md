# ClipMint — native Linux clipboard & screen capture

Early **v0.1 development prototype** for Linux Mint Cinnamon with **X11**. Independent of the Windows application ClipClip.

## Features implemented

- Persistent local text/image clipboard history, search, pin and delete.
- Right-click a snippet for **Copy**, **Pin / Unpin**, and **Delete**.
- Select a screenshot rectangle with the mouse; save PNG and copy image.
- Select a video rectangle with the mouse; record an MP4 through FFmpeg.
- Visible Stop recording button and optional tray Stop action.
- Pause/resume monitoring; open recordings folder.
- **No Wine or mandatory keyboard shortcuts.** Does not modify CopyQ.

## Install on Linux Mint

    git clone https://github.com/cryogenized-spec/clipmint-linux.git
    cd clipmint-linux
    bash install.sh
    bash run.sh

Private repositories need GitHub authentication for clone. Alternatively, use Code > Download ZIP on GitHub, extract, then run the scripts inside the extracted directory.

The installer installs FFmpeg, Python venv, and Qt XCB cursor support, then installs PySide6 into a project-local environment. Review the scripts before running. Run as your normal user, not root.

Click **Screenshot area** or **Record area**, drag a rectangle and release. Right-click on the selection overlay to cancel. Click **Stop recording** to save the MP4.

Files are saved in ~/Pictures/ClipMint and ~/Videos/ClipMint. Clipboard history is in ~/.local/share/clipmint/history.sqlite3 unless XDG_DATA_HOME is set.

## Development and testing

    python3 -m unittest discover -s tests -v
    python3 -m compileall -q clipmint tests

GitHub Actions runs the Python syntax and database tests. The GUI and actual X11 recording have **not** been tested on this user's Cinnamon machine. This is not a production-tested release.

## Limitations and security

Clipboard history is unencrypted. Pause monitoring before copying secrets and delete sensitive clips already stored. Primary display only; audio recording, annotation, OCR, Wayland, rich-text preservation, packaged .deb and automatic updates are not yet implemented. The ClipMint window may overlap the video capture region; minimize or move it after recording starts, then use the tray or window Stop control.

Licensed under MIT; not affiliated with ClipClip.
