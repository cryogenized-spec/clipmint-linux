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
first event-processing pass, live widget count and Linux process peak RSS.

The UI profile is a cold **window-construction** measurement, not a complete
cold-launch-to-visible-screen measurement. The benchmark does not simulate
X11 clipboard events, FTS index rebuilds for damaged databases, or real desktop
painting. These must be separately profiled before asserting end-user speedups.

SQLite queries must retain the data semantics and safety contracts established
by the existing unit tests. A faster result obtained by bypassing privacy,
plaintext/encrypted-history separation, pin protection, secret filtering or
the 1,000-result limit is invalid.
