# ClipMint Preview 340 — final beta acceptance record

**Status: controlled candidate / NOT APPROVED for general-public beta launch.**

**Reference release:** [clipmint-preview-340-1](https://github.com/cryogenized-spec/clipmint-linux/releases/tag/clipmint-preview-340-1)
**Reference commit:** `95c15fa9672419f7cccdfbfe6545dd3e59cc5e4b`
**Debian version:** `0.6.0~preview1.340.1` (`amd64`)
**Supported field environment:** Linux Mint 22, Cinnamon on X11, x86-64.

## Automated evidence captured 11 November 2026

- Merged into reference commit: [#91](https://github.com/cryogenized-spec/clipmint-linux/pull/91) cold capture/sidebar improvements, [#92](https://github.com/cryogenized-spec/clipmint-linux/pull/92) history-count/footer optimization, and [#94](https://github.com/cryogenized-spec/clipmint-linux/pull/94) history badges, screenshot copy, native drag.
- [Python and Qt checks](https://github.com/cryogenized-spec/clipmint-linux/actions/runs/43074081174): success; 437 unit/Qt tests (five skipped), plus a separate X11 clipboard run (five passing tests).
- [Build and publish](https://github.com/cryogenized-spec/clipmint-linux/actions/runs/43074081158): success; frozen executable, Debian package install/launch, virtual-X11 MP4/GIF recording, published immutable prerelease assets and differential packages.
- [Synthetic performance](https://github.com/cryogenized-spec/clipmint-linux/actions/runs/43074081053): success on a GitHub runner, **not** a physical Mint performance certification.
- Package file `clipmint_0.6.0.preview1.340.1_amd64.deb`: 122,116,552 bytes; GitHub-reported digest `a0f4c393bbe5aef399a9d5d683d862ab2b47c5b227fa135ea2fa062e2745391e`.
- Published differential from 336.1: 74,710 bytes; from 227.1: 4,710,775 bytes. Applies only to the matching exact base version and a corresponding retained original installer.

These are *GitHub release metadata and CI logs*, not an independent local rehash. Release checksums detect corruption but are not independent publisher signatures.

## Gate 1 — reproducible package identity

- [ ] On a clean download, save the **same-release** `.deb` and `SHA256SUMS` to one folder, verify `sha256sum --check SHA256SUMS` without errors.
- [ ] Confirm the file is `amd64`, package name is `clipmint`, and Debian version is `0.6.0~preview1.340.1` using `dpkg-deb -f NAME Package Version Architecture` (replace `NAME` with the actual file path).
- [ ] Confirm that every `DELTA*.json` names an existing patch with matching filename, size and hash. CI has checked these; independently recheck the published release if possible.
- [ ] Confirm no package maintainer scripts perform unexpected privileged actions.

## Gate 2 — real Linux Mint acceptance (exact final candidate)

Use synthetic clipboard samples, a disposable test profile where practical, and back up existing ClipMint history before an upgrade. Never upload real clipboard databases or sensitive screenshots to GitHub.

- [ ] Record OS, architecture, display session and installed package version; confirm X11 and Cinnamon.
- [ ] Check fresh install, launch, explicit Quit, close-to-background monitoring, restart and persistence; fully Quit must not replay old clipboard contents on next start.
- [ ] Check cold and warm `Ctrl+Shift+S` responsiveness, cancel/save behavior, no main-window flash or foreground theft.
- [ ] Check MP4 region start/stop/save/discard, actual playback, recovery from failed capture and no orphaned FFmpeg process.
- [ ] Check fast Clipboard/Screenshots/Recordings/Vault/Autosort/Settings navigation with small and large synthetic histories; record measurements on this laptop rather than assuming GitHub timings.
- [ ] Verify visible TEXT/IMAGE/LINK/FILES/CODE/HEX badges without polluting copied payloads.
- [ ] Verify screenshot gallery **Copy image** sends full-resolution data to an image editor without creating duplicate history entries.
- [ ] Verify native copy-only dragging of long text and links, and image/file upload drops where Firefox accepts the MIME types; confirm no unsafe secret drag or temporary-file leak.
- [ ] Check idle CPU/RSS, suspend/resume, hotkey re-registration and clipboard ownership after source program exit.
- [ ] Check keyring-enabled encrypted history and failure handling using a disposable test profile only.
- [ ] Test upgrade from the currently installed version without losing history, and test removal on a disposable installation; do not delete personal history to prove uninstall behavior.

## Gate 3 — release consent, privacy and rights

- [ ] Confirm automatic checks are opt-in and background package downloading/staging is disabled in this beta, including older saved settings.
- [ ] Confirm a manual Check downloads no package and a manual Download displays the possible **full 122 MB** transfer before explicit approval. A small patch is never promised unless the exact base installer exists.
- [ ] Keep the 20 MiB ceiling for any future permitted automatic patch transfer; no silent `sudo`, download, or installation.
- [ ] Confirm README and SECURITY warn that regular history is plaintext by default, encryption is opt-in, and the vault is experimental, not a password manager.
- [ ] Resolve image redistribution permissions, or replace assets: [#95](https://github.com/cryogenized-spec/clipmint-linux/issues/95). **Unresolved rights are stop-ship for broad public redistribution.**
- [ ] Document unsigned release authenticity limitations while [#63](https://github.com/cryogenized-spec/clipmint-linux/issues/63) remains open; never call the release independently signed/authenticated.
- [ ] Check remaining roadmap/issues [#9](https://github.com/cryogenized-spec/clipmint-linux/issues/9), [#26](https://github.com/cryogenized-spec/clipmint-linux/issues/26) and [#70](https://github.com/cryogenized-spec/clipmint-linux/issues/70) for explicit blocker/defer decisions.
- [ ] Record release approver, test date, final Git SHA/package digest, installation and rollback instructions, and release authorization.

## Important: release workflow change under review

The review branch `release/beta-acceptance-340` adds a CI package-removal/isolated-data-retention smoke test. This check did **not** run for the already published Preview 340. If merged, the branch will produce a **new** `main` commit and likely a new preview build: use that new exact package for final physical tests and sign-off. Do not transfer a pass from Preview 340 to a different artifact.

## Final sign-off

- Physical tester / environment: **pending**
- Rights/third-party redistribution: **pending (#95)**
- CI on any new candidate commit: **pending**
- Full local installer checksum verification: **pending**
- Final beta release authorization: **NOT APPROVED**
