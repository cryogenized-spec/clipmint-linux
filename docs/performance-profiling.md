# ClipMint reproducible performance baseline

This profiles **synthetic** clipboard records only; it never reads the real
clipboard, keyring, private database or personal configuration. Run from the
repository root with Python 3.12 and the package requirements installed.

```bash
python tools/profile_clipmint.py --case store --rows 400 --samples 25
QT_QPA_PLATFORM=offscreen python tools/profile_clipmint.py --case ui --rows 100
```

The GitHub Action **ClipMint synthetic performance baseline** runs each
scenario in a separate Python process on Ubuntu 24.04. Its job log prints
`CLIPMINT_PERFORMANCE_RESULT=` with a JSON object, and it uploads the two JSON
files as an artifact. Compare results only on like-for-like runner hardware,
environment, corpus size, versions and search mode. There are no performance
pass/fail limits: normal CI variance should not block corrective changes.

Metrics: SQLite open/reopen, corpus seed time, median/p95 search and duplicate
latency, first Qt import, QApplication creation, main-window constructor,
first event-processing pass, **navigation switch-pair latency**
(Settings↔Vault, Screenshots↔Recordings, Settings↔Clipboard),
live widget count and Linux process peak RSS.

The UI workflow now profiles both a 100-row baseline and a larger 500-row
synthetic archive. Each profile uses a temporary HOME as well as temporary
XDG data/config directories, so navigation never scans or creates archives
under the operator's real ~/Pictures or ~/Videos. Library scans skip unchanged
directory metadata on repeated navigation; the visible Refresh archive button
still forces a rescan (including images edited in place).

The UI profile measures cold **window construction** and synthetic section
switches, not real cold-launch-to-visible-screen time. It does not simulate
physical Cinnamon shortcuts, X11 IPC/screenshot latency, compositor painting,
real disk contention, FTS rebuilds for damaged databases or real-world image
archives. These must be measured on the user's Linux Mint laptop before
asserting end-to-end speedups or sub-second capture selectors.

SQLite queries must retain the data semantics and safety contracts established
by the existing unit tests. A faster result obtained by bypassing privacy,
plaintext/encrypted-history separation, pin protection, secret filtering or
the 1,000-result limit is invalid.
