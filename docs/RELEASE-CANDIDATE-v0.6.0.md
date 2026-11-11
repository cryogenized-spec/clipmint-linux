# ClipMint v0.6.0 — beta release candidate gates

Status: **candidate preparation, NOT release-approved**. Supported target:
Linux Mint 22, Cinnamon on X11, x86-64. This is a manual-update public beta,
not a stable or independently security-certified password manager.

The release manager must mark all mandatory checks complete before publishing
a **new candidate** or advertising this build as ready. Run physical acceptance
on the exact installed candidate, not an older preview or a GitHub runner.
Do not publish a signed/verified claim until the independently authenticated
release-manifest work in issue #63 is genuinely implemented.

## Gate A — source and CI

- [ ] PR #91 (cold capture + navigation) merged after all final-head required CI checks pass.
- [ ] PR #92 (history count + footer repaint) rebased onto merged `main`, fully verified and merged.
- [ ] No unresolved release-blocking regressions in Python/Qt, native visual,
      screenshots, X11/FFmpeg, archive/differential, or Debian installer CI.
- [ ] Record exact release candidate commit SHA and resulting Debian version.
- [ ] Confirm a clean package installation and clean removal on the CI runner.
- [ ] Reconcile outstanding issues #9, #26 and #70: close resolved items with
      specific supporting tests; explicitly defer nonblocking enhancements.
- [ ] Confirm AGPL-3.0 and third-party software/illustration redistribution
      rights; do not assume bundled character artwork is AGPL-licensed.

## Gate B — physical Linux Mint acceptance

Use the actual machine and session. Work with synthetic clipboard content,
never passwords or customer records. Avoid installing a candidate in the
middle of a working day. Back up existing application data first.

- [ ] Record `uname -m`, Mint version, `echo $XDG_SESSION_TYPE`,
      `dpkg-query -W -f='${Version}' clipmint` and whether the app was
      previously installed. **Do not attach private clipboard databases.**
- [ ] Cold boot the app with monitoring off, then opt in; no surprise import
      of text copied while ClipMint was fully quit.
- [ ] Close the main window. Copy synthetic text from another program.
      Reopen ClipMint and confirm history survived, then use **Quit** and
      verify background monitoring stops.
- [ ] Check Ctrl+Shift+S: first cold invocation (fully quit) and warm
      invocation (running but window hidden). The region selector should
      appear promptly and without flashing the full archive. Save one image;
      cancel another; confirm the correct foreground restoration.
- [ ] Check region MP4 capture with explicit Start/Stop, approved save/cancel,
      playback, recovery from recorder failure, and no uncontrolled FFmpeg
      subprocess after Quit.
- [ ] Exercise clipboard Quick Popup keyboard navigation, Copy and plain-text
      paste in editor, terminal and browser (with synthetic content).
- [ ] Visit Clipboard, Screenshots, Recordings, Vault, Autosort and Settings
      repeatedly. Confirm quick transitions, unchanged gallery content,
      an added file appearing without manual relaunch, and explicit Refresh
      detecting edited-in-place images.
- [ ] Copy image/text/HTML/Nemo file paths where supported; verify X11
      clipboard ownership after the source application exits.
- [ ] Test resuming after suspend/restart and opt-in start-at-login.
- [ ] Test a non-secret faux credential and known concealment MIME hint:
      sensitive items must never persist in ordinary history.
- [ ] Opt into history encryption in a disposable test profile, restart with
      keyring available/unavailable, verify fail-closed behavior and the
      explicit legacy-database cleanup option. Never erase the real user's
      history merely to test migration.
- [ ] Check startup, hotkey-to-overlay and sidebar switching with ordinary
      and large synthetic history. Measure on the same laptop before and
      after; CI timing alone does not prove end-user performance.
- [ ] Verify idle CPU/RSS and no significant event-loop stalls while hidden.
- [ ] Verify Mint's installer reports the intended package name/version,
      installs and uninstalls cleanly without deleting existing user history.

## Gate C — release trust, data costs and consent

- [ ] Automatic background **downloads/staging** blocked, including saved
      old opt-in preferences. Automatic checks may be explicitly enabled,
      at most once per day.
- [ ] Manual update *Check* never downloads any package. Manual *Download*
      displays the full possible installer size and requests explicit consent;
      small-patch reconstruction has 20 MiB data guard for any future
      automated staging path. Installation always asks through Mint.
- [ ] Package SHA-256 and Debian identity match the release; make clear these
      are integrity checks and **not independent publisher authentication**.
- [ ] The unsigned-release trust limitation and opt-in encrypted-history
      limitations are prominently visible in README and SECURITY.
- [ ] Release assets, checksums, delta manifests, optional bootstrap script
      and source commit are internally consistent.
- [ ] No runtime downloads of Python/Qt/FFmpeg/font dependencies; no telemetry,
      silent privileged installation, or new auto-start on existing profiles.

## Sign-off

- Candidate git SHA: `not assigned`
- Candidate .deb / version: `not assigned`
- CI: `pending`
- Linux Mint acceptance operator and date: `pending`
- Privacy/security review: `pending`
- Release authorisation: `NOT APPROVED`

**Stop ship:** missing/failed CI; crash, data corruption or unexpected data
deletion; capture hotkey failure or sustained UI freeze on Mint; silent package
download/install; loss of clipboard privacy gates; absent rights to redistribute
bundled artwork. A manual-update beta may document that independent publisher
signing (issue #63) is still pending, but must not promise authenticated releases.

Release process: only after all mandatory checks, freeze the commit, build
the exact package on the existing isolated CI job, verify assets, publish a
clearly marked prerelease, and attach concise installation and rollback notes.
