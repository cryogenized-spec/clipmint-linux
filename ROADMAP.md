# ClipMint roadmap

ClipMint remains a **preview**. This is a prioritized engineering backlog, not a commitment to ship untested features or a promise of release dates.

## P0 — Security and correctness

- [x] Preserve explicit opt-in and a 20 MiB ceiling for automatic preview patch downloads.
- [x] Require exact base/target checksums and explicit manual approval before Linux Mint package installation.
- [ ] Independently authenticate releases: owner-controlled offline signing key, pinned public verification key, signed immutable release manifest, key rotation and revocation procedure. **Do not call checksum-only releases authenticated.**
- [ ] Audit workflow tokens, action provenance and third-party dependencies, minimizing permissions and avoiding auto-commits from cosmetic review jobs.
- [ ] Fix recorder cancel restoring controls; test cancellation and failed startup states.
- [ ] Resolve ownership and redistribution licences for the maid and Kohaku images before claiming an unqualified asset licence.

## P1 — Updates, metered connections and maintainability

- [ ] Benchmark end-to-end update time, CPU/RAM/disk I/O, and network transfer on physical Linux Mint/X11.
- [ ] Design smaller application-only packages with a stable runtime; evaluate signed APT repositories versus the current custom exact-byte `.deb` reconstruction. **APT metadata signing does not itself make every package update differential.**
- [ ] Add visible update-stage and error progress without blocking clipboard capture.
- [ ] Create reproducible and reviewed locked build dependencies; introduce Ruff and incremental type checking without creating a large noise-only diff.
- [ ] Split the large `ClipMintWindow` class into UI/controller boundaries: recorder, history, updater, popup and preferences. Preserve the working screenshot shortcut path.

## P2 — Privacy and real-device QA

- [ ] Review encrypted history opt-in and recovery-copy lifecycle. Test safe default encryption **only** when Secret Service availability, backup and recovery have been covered.
- [ ] Independently review the experimental vault, benchmark Argon2id parameters, and preserve compatibility with existing encrypted vaults.
- [ ] Run actual Xvfb+FFmpeg recording tests checking non-black video, duration and usable frame count, in addition to unit tests.
- [ ] Test screenshot/recording shortcuts on real multi-monitor Cinnamon/X11 hardware, clipboard persistence after window closure, login/autostart and full shutdown.
- [ ] Reduce duplicate images and historical generated artifacts in Git history without destroying original artistic source assets.

## Release gates

Every build must pass Python/Qt tests and Debian package inspection. Updates also require independent release authentication before being marketed as fully trusted. A passing CI build is **not** equivalent to an on-device acceptance test. No automatic privileged installation; no silent full-installer downloads.
