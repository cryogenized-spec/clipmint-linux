# ClipMint — Field Prototype Acceptance Checklist

**Target:** Linux Mint 22 Cinnamon/X11, x86-64. **Status:** preview, not production software.

## Install / upgrade without a terminal

1. Quit any older ClipMint from its system tray before upgrading (and finish any recording).
2. Open https://github.com/cryogenized-spec/clipmint-linux/releases and download the .deb file from the newest *successful* field-prototype release.
3. Double-click the .deb in Nemo/Files and choose **Install Package**. Enter your normal administrator password if prompted.
4. Open **ClipMint** from the application menu. No Wine, command prompt, pip, or separate FFmpeg installation required.
5. If Linux Mint asks to download additional software, **stop** and report it as a packaging failure; the target is offline installation.
6. For upgrades, preserve the database in ~/.local/share/clipmint/history.sqlite3. Existing entries should be migrated to the Work bin. Back up valuable entries before testing an experimental release.

## Manual field tests (mouse-first)

| Test | Action | Expected result |
| --- | --- | --- |
| 01 | Launch from Cinnamon menu | Window opens without a terminal |
| 02 | Copy safe text in another application | Clip appears in active bin |
| 03 | Switch Work/Personal/Temporary and copy different text | Histories stay independent |
| 04 | Right-click Copy then paste elsewhere | Correct snippet pasted |
| 05 | Pin, Move, Delete, Search, A–Z and Latest first | Functions update correctly |
| 06 | Click Screenshot | Full primary screen is saved |
| 07 | Screenshot dropdown: Select area | Mouse-drag region saved as PNG |
| 08 | Open capture from Screenshots | Default desktop image application opens |
| 09 | Record a short region MP4, High quality | Floating controller shows timer/estimated size |
| 10 | Stop, choose No with arrows, press Enter | Pending clip discarded |
| 11 | Repeat recording and press Enter on highlighted Yes | MP4 appears in Recordings and plays |
| 12 | Record GIF from format menu | GIF saved and opens |
| 13 | Reopen application after closing main window | History persists; tray/menu reopen correctly |
| 14 | Disconnect Wi-Fi then relaunch | No network/download is needed |
| 15 | Upgrade previous ClipMint with sample history | Existing entries remain, no reset |

## Report any failure

Record the test number, exact error text, MP4 or GIF, selected quality, number of monitors and relevant actions taken. Include a screenshot only when it contains no private messages, passwords or tokens.

## Known limits

X11 only; primary-screen area selector; silent video (no audio); the control panel may show in fullscreen recording; clipboard history is unencrypted and not a password vault; Autosort is basic type filtering rather than custom rules; aborted recordings may leave a hidden pending file. Screenshot and recording behaviour on the actual laptop remains unverified until this checklist is completed.

**Data locations:** ~/.local/share/clipmint/history.sqlite3, ~/Pictures/ClipMint, ~/Videos/ClipMint.
**Desktop build validation:** GitHub CI tests the installed package, its launcher and short MP4/GIF output on a virtual X11 display.
